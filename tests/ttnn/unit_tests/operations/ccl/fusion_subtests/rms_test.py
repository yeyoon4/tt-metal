# SPDX-FileCopyrightText: © 2025 Tenstorrent Inc.

# SPDX-License-Identifier: Apache-2.0

import torch
import pytest
from loguru import logger
import ttnn
import math
from tests.tt_eager.python_api_testing.sweep_tests.comparison_funcs import comp_equal, comp_pcc
from models.utility_functions import skip_for_grayskull
from models.perf.benchmarking_utils import BenchmarkData, BenchmarkProfiler
from tracy import signpost


def get_torch_rms(x, dim, gamma, beta, eps):
    return x * torch.rsqrt(x.pow(2).mean([-i for i in range(1, len(dim) + 1)], keepdim=True) + eps) * gamma + beta


def run_rms_trace(
    mesh_device,
    num_devices,
    elements_per_batch,
    num_links,
    use_program_cache,
    function_level_defaults,
    input_shard_grid,
    output_shard_grid,
    all_gather_topology,
    num_iters=1,
    input_dtype=ttnn.bfloat8_b,
    layout=ttnn.TILE_LAYOUT,
    topology=ttnn.Topology.Linear,
    epsilon=1e-05,
    warmup_iters=0,
    use_new_version=True,
    profiler=BenchmarkProfiler(),
):
    ccl_sub_device_crs = ttnn.CoreRangeSet({ttnn.CoreRange(ttnn.CoreCoord(0, 0), ttnn.CoreCoord(7, 1))})
    worker_sub_device = ttnn.SubDevice(
        [
            ccl_sub_device_crs,
        ]
    )
    worker_sub_device_id = ttnn.SubDeviceId(0)
    sub_device_stall_group = [worker_sub_device_id]
    sub_device_manager = mesh_device.create_sub_device_manager([worker_sub_device], 0)
    mesh_device.load_sub_device_manager(sub_device_manager)
    mesh_device.set_sub_device_stall_group(sub_device_stall_group)
    torch.manual_seed(1234)
    num_cores = input_shard_grid.num_cores()
    total_cores = num_cores * num_devices
    padded_dim_per_core = int(math.ceil(elements_per_batch / total_cores / 32) * 32)
    padded_dim = padded_dim_per_core * total_cores

    size_per_device = padded_dim // num_devices
    input_shape = (1, 1, 32, padded_dim)
    input_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            32,
            padded_dim_per_core,
        ),
        core_grid=input_shard_grid,
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )

    layer_norm_config = ttnn.LayerNormShardedMultiCoreProgramConfig(
        compute_with_storage_grid_size=(8, 2),
        subblock_w=1,
        block_h=1,
        block_w=(size_per_device // num_cores) // 32,
        inplace=False,
    )

    ccl_semaphore_handles = ttnn.create_global_semaphore(mesh_device, input_shard_grid, 0)

    ag_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            32,
            128,
        ),
        core_grid=ttnn.CoreRangeSet({ttnn.CoreRange(ttnn.CoreCoord(0, 0), ttnn.CoreCoord(0, 0))}),
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )

    output_pad_width = math.ceil(padded_dim_per_core / num_devices / 32) * 32
    if output_shard_grid is None:
        output_shard_grid = input_shard_grid
    padded_out_w = math.ceil(input_shape[3] / num_devices / output_shard_grid.num_cores() / 32) * 32
    output_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            input_shape[0] * input_shape[1] * input_shape[2],
            output_pad_width * num_devices,
        ),
        core_grid=output_shard_grid,
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )
    input_tensor_torch = torch.randn(input_shape)
    gamma_torch = torch.randn((1, 1, 1, input_shape[3]))
    input_tensor = ttnn.as_tensor(
        input_tensor_torch,
        dtype=input_dtype,
        device=mesh_device,
        mesh_mapper=ttnn.ShardTensor2dMesh(
            mesh_device=mesh_device, dims=(None, 3), mesh_shape=list(ttnn.MeshShape(1, num_devices))
        ),
        layout=layout,
        memory_config=input_memory_config,
    )
    gamma_tensor = ttnn.as_tensor(
        gamma_torch.reshape(
            [
                1,
                1,
                padded_dim // 32,
                32,
            ]
        ),
        dtype=ttnn.bfloat16,
        device=mesh_device,
        mesh_mapper=ttnn.ShardTensor2dMesh(
            mesh_device=mesh_device, dims=(None, 2), mesh_shape=list(ttnn.MeshShape(1, num_devices))
        ),
        layout=ttnn.ROW_MAJOR_LAYOUT,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
    )
    logger.info("Compiling model")
    if use_new_version:
        tt_stats = ttnn.fused_rms_1_1_32_8192(
            input_tensor,
            layer_norm_config,
            1,
            mesh_device,
            ccl_semaphore_handles,
            is_pre=True,
        )
        tt_out = ttnn.fused_rms_1_1_32_8192(
            input_tensor,
            layer_norm_config,
            1,
            mesh_device,
            ccl_semaphore_handles,
            dtype=ttnn.bfloat8_b,
            memory_config=output_memory_config,
            epsilon=epsilon,
            weight=gamma_tensor,
            stats=tt_stats,
            is_pre=False,
        )

        logger.info("Capturing trace")
        if warmup_iters > 0:
            trace_id_warmup = ttnn.begin_trace_capture(mesh_device, cq_id=0)
            for _ in range(warmup_iters):
                tt_stats = ttnn.fused_rms_1_1_32_8192(
                    input_tensor,
                    layer_norm_config,
                    1,
                    mesh_device,
                    ccl_semaphore_handles,
                    is_pre=True,
                )
                # tt_out = ttnn.fused_rms_1_1_32_8192(
                #    input_tensor,
                #    layer_norm_config,
                #    1,
                #    mesh_device,
                #    ccl_semaphore_handles,
                #    dtype=ttnn.bfloat8_b,
                #    memory_config=output_memory_config,
                #    epsilon=epsilon,
                #    weight=gamma_tensor,
                #    stats=tt_stats,
                #    is_pre=False,
                # )
            ttnn.end_trace_capture(mesh_device, trace_id_warmup, cq_id=0)
            logger.info("Done warmup")
            ttnn.synchronize_device(mesh_device)
        trace_id = ttnn.begin_trace_capture(mesh_device, cq_id=0)
        for _ in range(num_iters):
            tt_stats = ttnn.fused_rms_1_1_32_8192(
                input_tensor,
                layer_norm_config,
                1,
                mesh_device,
                ccl_semaphore_handles,
                is_pre=True,
            )
            # tt_out = ttnn.fused_rms_1_1_32_8192(
            #    input_tensor,
            #    layer_norm_config,
            #    1,
            #    mesh_device,
            #    ccl_semaphore_handles,
            #    dtype=ttnn.bfloat8_b,
            #    memory_config=output_memory_config,
            #    epsilon=epsilon,
            #    weight=gamma_tensor,
            #    stats=tt_stats,
            #    is_pre=False,
            # )
        ttnn.end_trace_capture(mesh_device, trace_id, cq_id=0)
    else:
        tt_stats = ttnn.rms_norm_pre_all_gather(
            input_tensor,
            program_config=layer_norm_config,
        )
        tt_stats_gathered = ttnn.experimental.all_gather_async(
            tt_stats,
            3,
            ccl_semaphore_handles,
            num_links=num_links,
            topology=ttnn.Topology.Linear,
            memory_config=ag_memory_config,
        )

        tt_out = ttnn.rms_norm_post_all_gather(
            input_tensor,
            tt_stats_gathered,
            program_config=layer_norm_config,
            dtype=ttnn.bfloat8_b,
            memory_config=output_memory_config,
            epsilon=epsilon,
            weight=gamma_tensor,
        )

        logger.info("Capturing trace")
        if warmup_iters > 0:
            trace_id_warmup = ttnn.begin_trace_capture(mesh_device, cq_id=0)
            for _ in range(warmup_iters):
                tt_stats = ttnn.rms_norm_pre_all_gather(
                    input_tensor,
                    program_config=layer_norm_config,
                )
                tt_stats_gathered = ttnn.experimental.all_gather_async(
                    tt_stats,
                    3,
                    ccl_semaphore_handles,
                    num_links=num_links,
                    topology=ttnn.Topology.Linear,
                    memory_config=ag_memory_config,
                )
                tt_out = ttnn.rms_norm_post_all_gather(
                    input_tensor,
                    tt_stats_gathered,
                    program_config=layer_norm_config,
                    dtype=ttnn.bfloat8_b,
                    memory_config=output_memory_config,
                    epsilon=epsilon,
                    weight=gamma_tensor,
                )
            ttnn.end_trace_capture(mesh_device, trace_id_warmup, cq_id=0)
            logger.info("Done warmup")
            ttnn.synchronize_device(mesh_device)
        trace_id = ttnn.begin_trace_capture(mesh_device, cq_id=0)
        for _ in range(num_iters):
            tt_stats = ttnn.rms_norm_pre_all_gather(
                input_tensor,
                program_config=layer_norm_config,
            )
            tt_stats_gathered = ttnn.experimental.all_gather_async(
                tt_stats,
                3,
                ccl_semaphore_handles,
                num_links=num_links,
                topology=ttnn.Topology.Linear,
                memory_config=ag_memory_config,
            )
            tt_out = ttnn.rms_norm_post_all_gather(
                input_tensor,
                tt_stats_gathered,
                program_config=layer_norm_config,
                dtype=ttnn.bfloat8_b,
                memory_config=output_memory_config,
                epsilon=epsilon,
                weight=gamma_tensor,
            )
        ttnn.end_trace_capture(mesh_device, trace_id, cq_id=0)
    logger.info("Starting Trace perf test...")

    profiler.start("rms-trace-warmup")
    if warmup_iters > 0:
        ttnn.execute_trace(mesh_device, trace_id_warmup, blocking=False)
        ttnn.release_trace(mesh_device, trace_id_warmup)
        ttnn.synchronize_device(mesh_device)
    profiler.end("rms-trace-warmup")

    signpost("start")
    profiler.start("rms-trace")

    ttnn.execute_trace(mesh_device, trace_id, blocking=False)
    ttnn.release_trace(mesh_device, trace_id)
    ttnn.synchronize_device(mesh_device)
    profiler.end("rms-trace")
    signpost("stop")
    time_taken = profiler.get_duration("rms-trace") - profiler.get_duration("rms-trace-warmup")
    mesh_device.reset_sub_device_stall_group()


def run_rms_fuse_impl(
    mesh_device,
    num_devices,
    elements_per_batch,
    num_links,
    use_program_cache,
    function_level_defaults,
    input_shard_grid,
    output_shard_grid,
    all_gather_topology,
    num_iters=1,
    input_dtype=ttnn.bfloat8_b,
    layout=ttnn.TILE_LAYOUT,
    topology=ttnn.Topology.Linear,
    epsilon=1e-05,
):
    ccl_sub_device_crs = ttnn.CoreRangeSet({ttnn.CoreRange(ttnn.CoreCoord(0, 0), ttnn.CoreCoord(7, 1))})
    worker_sub_device = ttnn.SubDevice(
        [
            ccl_sub_device_crs,
        ]
    )
    worker_sub_device_id = ttnn.SubDeviceId(0)
    sub_device_stall_group = [worker_sub_device_id]
    sub_device_manager = mesh_device.create_sub_device_manager([worker_sub_device], 0)
    mesh_device.load_sub_device_manager(sub_device_manager)
    mesh_device.set_sub_device_stall_group(sub_device_stall_group)
    torch.manual_seed(1234)
    num_cores = input_shard_grid.num_cores()
    total_cores = num_cores * num_devices
    padded_dim_per_core = int(math.ceil(elements_per_batch / total_cores / 32) * 32)
    padded_dim = padded_dim_per_core * total_cores
    size_per_device = padded_dim // num_devices
    input_shape = (1, 1, 32, padded_dim)
    input_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            32,
            padded_dim_per_core,
        ),
        core_grid=input_shard_grid,
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )
    layer_norm_config = ttnn.LayerNormShardedMultiCoreProgramConfig(
        compute_with_storage_grid_size=(8, 2),
        subblock_w=1,
        block_h=1,
        block_w=(size_per_device // num_cores) // 32,
        inplace=False,
    )
    ccl_semaphore_handles = [ttnn.create_global_semaphore(mesh_device, input_shard_grid, 0) for _ in range(num_iters)]
    ag_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            32,
            256,
        ),
        core_grid=input_shard_grid,
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )
    output_pad_width = math.ceil(padded_dim_per_core / num_devices / 32) * 32
    if output_shard_grid is None:
        output_shard_grid = input_shard_grid
    padded_out_w = math.ceil(input_shape[3] / num_devices / output_shard_grid.num_cores() / 32) * 32
    output_memory_config = ttnn.create_sharded_memory_config(
        shape=(
            input_shape[0] * input_shape[1] * input_shape[2],
            output_pad_width * 8,
        ),
        core_grid=output_shard_grid,
        strategy=ttnn.ShardStrategy.WIDTH,
        orientation=ttnn.ShardOrientation.ROW_MAJOR,
        use_height_and_width_as_shard_shape=True,
    )
    input_tensor_torch = []
    gamma_torch = []
    input_tensor = []
    gamma_tensor = []
    tt_out_array = []
    for i in range(num_iters):
        input_tensor_torch.append(torch.randn(input_shape))
        gamma_torch.append(torch.randn((1, 1, 1, input_shape[3])))
        input_tensor.append(
            ttnn.as_tensor(
                input_tensor_torch[i],
                dtype=input_dtype,
                device=mesh_device,
                mesh_mapper=ttnn.ShardTensor2dMesh(
                    mesh_device=mesh_device, dims=(None, 3), mesh_shape=list(ttnn.MeshShape(1, num_devices))
                ),
                layout=layout,
                memory_config=input_memory_config,
            )
        )
        gamma_tensor.append(
            ttnn.as_tensor(
                gamma_torch[i].reshape(
                    [
                        1,
                        1,
                        padded_dim // 32,
                        32,
                    ]
                ),
                dtype=ttnn.bfloat16,
                device=mesh_device,
                mesh_mapper=ttnn.ShardTensor2dMesh(
                    mesh_device=mesh_device, dims=(None, 2), mesh_shape=list(ttnn.MeshShape(1, num_devices))
                ),
                layout=ttnn.ROW_MAJOR_LAYOUT,
                memory_config=ttnn.DRAM_MEMORY_CONFIG,
            )
        )
    for i in range(num_iters):
        tt_stats = ttnn.fused_rms_1_1_32_8192(
            input_tensor[i],
            layer_norm_config,
            1,
            mesh_device,
            ccl_semaphore_handles[i],
            is_pre=True,
        )
        tt_out = ttnn.fused_rms_1_1_32_8192(
            input_tensor[i],
            layer_norm_config,
            1,
            mesh_device,
            ccl_semaphore_handles[i],
            dtype=ttnn.bfloat8_b,
            memory_config=output_memory_config,
            epsilon=epsilon,
            weight=gamma_tensor[i],
            stats=tt_stats,
            is_pre=False,
        )
        tt_out_array.append(tt_out)
        ttnn.deallocate(tt_stats)
    for i in range(num_iters):
        tt_out_torch = ttnn.to_torch(
            tt_out_array[i],
            mesh_composer=ttnn.ConcatMesh2dToTensor(mesh_device, dims=(0, 3), mesh_shape=(1, num_devices)),
        )[0].unsqueeze(0)
        ref_lnorm = get_torch_rms(input_tensor_torch[i], [3], gamma_torch[i], torch.zeros_like(gamma_torch[i]), epsilon)
        passing, output = comp_pcc(tt_out_torch, ref_lnorm, 0.999)
        logger.info(output)
        if not passing:
            mesh_device.reset_sub_device_stall_group()
        assert passing
    mesh_device.reset_sub_device_stall_group()

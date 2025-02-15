# SPDX-FileCopyrightText: © 2023 Tenstorrent Inc.

# SPDX-License-Identifier: Apache-2.0

import pytest

import torch

import ttnn
from tests.ttnn.utils_for_testing import assert_with_pcc


@pytest.mark.parametrize("batch_size", [1, 16])
@pytest.mark.parametrize("h", [32, 64])
@pytest.mark.parametrize("w", [32, 64])
@pytest.mark.parametrize("dim", [-1, -2])
def test_std(device, batch_size, h, w, dim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((batch_size, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.std(torch_input_tensor, dim=dim, keepdim=True)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.std(input_tensor, dim=dim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("batch_size", [1, 16])
@pytest.mark.parametrize("h", [32, 64])
@pytest.mark.parametrize("w", [32, 64])
@pytest.mark.parametrize("dim", [-1, -2])
def test_var(device, batch_size, h, w, dim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((batch_size, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.var(torch_input_tensor, dim=dim, keepdim=True)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.var(input_tensor, dim=dim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("batch_size", [1])
@pytest.mark.parametrize("c", [11])
@pytest.mark.parametrize("h", [67])
@pytest.mark.parametrize("w", [77])
@pytest.mark.parametrize("dim", [0, 1, 2, 3])
@pytest.mark.parametrize("keepdim", [True, False])
def test_prod(device, batch_size, c, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((batch_size, c, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.prod(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(
        torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device, memory_config=ttnn.L1_MEMORY_CONFIG
    )

    output_tensor = ttnn.prod(input_tensor, dim=dim, keepdim=keepdim, memory_config=ttnn.L1_MEMORY_CONFIG)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert len(output_tensor.shape) == len(torch_output_tensor.shape)
    assert output_tensor.shape == torch_output_tensor.shape
    # assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("batch_size", [32])
@pytest.mark.parametrize("c", [32])
@pytest.mark.parametrize("h", [37])
@pytest.mark.parametrize("w", [63])
@pytest.mark.parametrize("dim", [None, [], 0, 2, [0, 1], [1, 3], [0, 1, 2], [1, 2, 3], [0, 1, 2, 3]])
@pytest.mark.parametrize("keepdim", [True])
def test_sum_4d_tensor_dims(device, batch_size, c, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((batch_size, c, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.sum(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.sum(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("c", [3])
@pytest.mark.parametrize("h", [31])
@pytest.mark.parametrize("w", [32])
@pytest.mark.parametrize("dim", [[0, 2], [0, 1, 2]])
@pytest.mark.parametrize("keepdim", [True])
def test_sum_3d_tensor_dims(device, c, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((c, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.sum(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.sum(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("h", [41])
@pytest.mark.parametrize("w", [31])
@pytest.mark.parametrize("dim", [0, 1, [0, 1]])
@pytest.mark.parametrize("keepdim", [True])
def test_sum_2d_tensor_dims(device, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.sum(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.sum(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("batch_size", [3])
@pytest.mark.parametrize("c", [5])
@pytest.mark.parametrize("h", [37])
@pytest.mark.parametrize("w", [63])
@pytest.mark.parametrize("dim", [None, [], 0, 2, [0, 1], [1, 3], [0, 1, 2], [1, 2, 3], [0, 1, 2, 3]])
@pytest.mark.parametrize("keepdim", [True])
def test_mean_4d_tensor_dims(device, batch_size, c, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((batch_size, c, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.mean(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.mean(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("c", [3])
@pytest.mark.parametrize("h", [31])
@pytest.mark.parametrize("w", [32])
@pytest.mark.parametrize("dim", [[0, 2], [0, 1, 2]])
@pytest.mark.parametrize("keepdim", [True])
def test_mean_3d_tensor_dims(device, c, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((c, h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.mean(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.mean(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)


@pytest.mark.parametrize("h", [41])
@pytest.mark.parametrize("w", [31])
@pytest.mark.parametrize("dim", [0, 1, [0, 1]])
@pytest.mark.parametrize("keepdim", [True])
def test_mean_2d_tensor_dims(device, h, w, dim, keepdim):
    torch.manual_seed(0)

    torch_input_tensor = torch.randn((h, w), dtype=torch.bfloat16)
    torch_output_tensor = torch.mean(torch_input_tensor, dim=dim, keepdim=keepdim)

    input_tensor = ttnn.from_torch(torch_input_tensor, layout=ttnn.TILE_LAYOUT, device=device)

    output_tensor = ttnn.mean(input_tensor, dim=dim, keepdim=keepdim)
    output_tensor = ttnn.to_layout(output_tensor, ttnn.TILE_LAYOUT)
    output_tensor = ttnn.from_device(output_tensor)

    output_tensor = ttnn.to_torch(output_tensor)
    assert_with_pcc(torch_output_tensor, output_tensor, pcc=0.99)

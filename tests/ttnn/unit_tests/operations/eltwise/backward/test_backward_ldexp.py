# SPDX-FileCopyrightText: © 2023 Tenstorrent Inc.

# SPDX-License-Identifier: Apache-2.0

import torch
import pytest
import ttnn
from tests.ttnn.unit_tests.operations.eltwise.backward.utility_funcs import (
    data_gen_with_range,
    compare_pcc,
    data_gen_with_range_dtype,
)


@pytest.mark.parametrize(
    "input_shapes",
    (
        (torch.Size([1, 1, 32, 32])),
        (torch.Size([1, 1, 320, 384])),
        (torch.Size([1, 3, 320, 384])),
    ),
)
def test_bw_ldexp(input_shapes, device):
    in_data, input_tensor = data_gen_with_range(input_shapes, -10, 10, device, True)
    other_data, other_tensor = data_gen_with_range(input_shapes, -20, 20, device, True)

    grad_data, grad_tensor = data_gen_with_range(input_shapes, -5, 5, device)

    tt_output_tensor_on_device = ttnn.ldexp_bw(grad_tensor, input_tensor, other_tensor)

    golden_function = ttnn.get_golden_function(ttnn.ldexp_bw)
    golden_tensor = golden_function(grad_data, in_data, other_data)
    comp_pass = compare_pcc(tt_output_tensor_on_device, golden_tensor)
    assert comp_pass


@pytest.mark.parametrize(
    "input_shapes",
    (
        (torch.Size([1, 1, 32, 32])),
        (torch.Size([1, 1, 320, 384])),
        (torch.Size([1, 3, 320, 384])),
    ),
)
def test_bw_ldexp_bf8b(input_shapes, device):
    in_data, input_tensor = data_gen_with_range_dtype(input_shapes, -10, 10, device, True, False, ttnn.bfloat8_b)
    other_data, other_tensor = data_gen_with_range_dtype(input_shapes, -20, 20, device, True, False, ttnn.bfloat8_b)

    grad_data, grad_tensor = data_gen_with_range_dtype(input_shapes, -5, 5, device, False, False, ttnn.bfloat8_b)

    tt_output_tensor_on_device = ttnn.ldexp_bw(grad_tensor, input_tensor, other_tensor)

    golden_function = ttnn.get_golden_function(ttnn.ldexp_bw)
    golden_tensor = golden_function(grad_data, in_data, other_data)
    comp_pass = compare_pcc(tt_output_tensor_on_device, golden_tensor)
    assert comp_pass

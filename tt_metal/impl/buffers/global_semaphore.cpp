// SPDX-FileCopyrightText: © 2024 Tenstorrent Inc.
//
// SPDX-License-Identifier: Apache-2.0

#include "tt_metal/impl/buffers/global_semaphore.hpp"

#include <cstdint>
#include <memory>
#include <vector>

#include "tt_metal/common/assert.hpp"
#include "tt_metal/common/core_coord.hpp"
#include "tt_metal/detail/tt_metal.hpp"
#include "tt_metal/host_api.hpp"
#include "tt_metal/impl/buffers/buffer.hpp"
#include "tt_metal/impl/buffers/buffer_constants.hpp"
#include "tt_metal/device.hpp"
#include "tt_metal/llrt/hal.hpp"

namespace tt::tt_metal {

GlobalSemaphore::GlobalSemaphore(
    IDevice* device,
    const CoreRangeSet& cores,
    uint32_t initial_value,
    BufferType buffer_type,
    tt::stl::Span<const SubDeviceId> sub_device_ids) :
    device_(device), cores_(cores) {
    this->setup_buffer(initial_value, buffer_type, sub_device_ids);
}

GlobalSemaphore::GlobalSemaphore(
    IDevice* device,
    CoreRangeSet&& cores,
    uint32_t initial_value,
    BufferType buffer_type,
    tt::stl::Span<const SubDeviceId> sub_device_ids) :
    device_(device), cores_(std::move(cores)) {
    this->setup_buffer(initial_value, buffer_type, sub_device_ids);
}

void GlobalSemaphore::setup_buffer(
    uint32_t initial_value, BufferType buffer_type, tt::stl::Span<const SubDeviceId> sub_device_ids) {
    TT_FATAL(
        buffer_type == BufferType::L1 or buffer_type == BufferType::L1_SMALL,
        "Global semaphore can only be created for L1 buffer types");
    TT_FATAL(this->device_ != nullptr, "Device cannot be null");
    TT_FATAL(this->cores_.num_cores() > 0, "CoreRangeSet must have at least one core");
    uint32_t num_cores = this->cores_.num_cores();
    auto shard_parameters =
        ShardSpecBuffer(this->cores_, {1, 1}, ShardOrientation::ROW_MAJOR, false, {1, 1}, {num_cores, 1});

    this->buffer_ = Buffer::create(
        this->device_,
        num_cores * sizeof(uint32_t),
        sizeof(uint32_t),
        buffer_type,
        TensorMemoryLayout::HEIGHT_SHARDED,
        shard_parameters,
        std::nullopt);

    this->reset_semaphore_value(initial_value, sub_device_ids);
}

IDevice* GlobalSemaphore::device() const { return device_; }

DeviceAddr GlobalSemaphore::address() const { return buffer_->address(); }

void GlobalSemaphore::reset_semaphore_value(
    uint32_t reset_value, tt::stl::Span<const SubDeviceId> sub_device_ids) const {
    // Write the initial value to the semaphore to the device
    // Only block for the slow dispatch case
    auto* device = this->device_;
    device->push_work([device,
                       reset_value,
                       sub_device_ids = std::vector<SubDeviceId>(sub_device_ids.begin(), sub_device_ids.end()),
                       num_cores = this->cores_.num_cores(),
                       buffer = this->buffer_] {
        std::vector<uint32_t> host_buffer(num_cores, reset_value);
        if (device->using_slow_dispatch()) {
            detail::WriteToBuffer(*buffer, host_buffer);
            tt::Cluster::instance().l1_barrier(device->id());
        } else {
            EnqueueWriteBuffer(device->command_queue(), buffer, host_buffer, false, sub_device_ids);
        }
    });
}

}  // namespace tt::tt_metal

namespace std {

std::size_t hash<tt::tt_metal::GlobalSemaphore>::operator()(
    const tt::tt_metal::GlobalSemaphore& global_semaphore) const {
    return tt::stl::hash::hash_objects_with_default_seed(global_semaphore.attribute_values());
}

}  // namespace std

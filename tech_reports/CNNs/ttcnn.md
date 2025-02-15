# Convolution Networks on Tenstorrent Chips

**Author**: Metalium CNN Team, Tenstorrent Inc.\
**Correspondence**: `asarje@tenstorrent.com`

## Abstract
In this paper we discuss the details of implementing Convolution Neural Networks (CNNs) on the Tenstorrent architectures. This includes the _Conv2D_ operation. We also detail the parallelization and performance optimizations, particularly focusing on the _sliding window operations_ in general and construction of fully local (to each core on the processors) data shards. An implementation of the ResNet-50 model using our Metalium stack.


Introduction
============

A Convolution Neural Network (CNN) is a type of deep learning model
particularly suited for processing data in a structured grid, such as
images. CNNs leverage convolution operations to automatically learn
spatial hierarchies of features from input data. These networks are
composed of layers that apply various filters to the input image,
capturing patterns and structures at multiple levels.

A convolution operation is a mathematical operation employed in the
training and inference of CNNs, which entails applying a filter (or
*kernel*), to the input to generate a feature map, highlighting
significant features within the input data. This operation is
characterized by its kernel window size, which determines the scope of
the input data each filter processes at a time.

When the window size is larger than $1$, the convolution operation
employs a sliding window technique. The window moves across the input
data, and at each pixel position, it computes the dot product of the
filter weights with the input image values. This results in a feature
map where each value represents the presence of features detected by the
filter. This ability to capture spatial relationships makes convolutions
highly effective.

In contrast, when the window size is exactly 1, the convolution
operation simplifies to a matrix multiplication operation. Here, each
input element is independently multiplied by the filter weight without
requiring any neighboring elements. This version is computationally
efficient but does not capture spatial relationships within the data.

Application of convolutions in CNNs are pivotal in tasks like image
recognition and object detection. CNNs are used in a large number of
real-world applications including video analysis, medical imaging
analysis, and natural language processing, where they can analyze data
to extract meaningful features and patterns.

## Convolution Operations in TTNN

### `conv2d`

Applies a 2D convolution over `input_tensor`, a 4D tensor with dimensions ordered as `(batch_size, input_height, input_width, in_channels)` using provided weights, with dimensions `(out_channels, in_channels, kernel_height, kernel_width)`, and optional `bias`, with dimensions `(1, 1, 1, out_channels)`, and generates `output_tensor` with first three dimensions flattened and ordered as `(1, 1, batch_size * output_height * output_width, out_channels)`. A simple `reshape` can be used to obtain the unflattened tensor.

#### Python API

```python
    output_tensor = ttnn.conv2d(
        input_tensor,
        weight_tensor,
        in_channels,
        out_channels,
        device,
        bias_tensor,
        kernel_size,
        stride,
        padding,
        dilation,
        batch_size,
        input_height,
        input_width,
        ## optional arguments
        conv_config,
        compute_config,
        groups,
        memory_config,
        return_weights_and_bias=False,
        return_output_dim=False,
    )
```

Arguments:

* `input_tensor`
* `weight_tensor`
* `bias_tensor`
* `in_channels` the number of input channels as an `int`.
* `out_channels` the number of output channels as an `int`.
* `device` device pointer as `ttnn.Device`.
* `kernel_size` tuple of two ints: `(kernel_height, kernel_width)`.
* `stride` tuple of two ints: `(stride_height, stride_width)`.
* `padding` tuple of two ints: `(padding_height, padding_width)`.
* `dilation` tuple of two ints: `(dilation_height, dilation_width)`.
* `batch_size` an `int`.
* `input_height` an `int`.
* `input_width` an `int`.
* `conv_config` _optional_ structure of configuration parameters of type `Conv2DConfig`. This is described in detail below.
* `compute_config` _optional_ structure of compute configuration parameters of type `DeviceConfiguration`. This is described in detail below.
* `groups` _optional_ `int` to control the connections between inputs and outputs. Both `in_channels` and `out_channels` should be divisible by `groups`.
* `memory_config` _optional_ output tensor memory configuration. This is described below.
* `return_weights_and_bias = False` _optional_ `bool` indicating whether to return pre-processed weights and bias tensors on device.
* `return_output_dim = False` _optional_ `bool` indicating whether to return the outout tensor height and width.

#### `Conv2dConfig`

Following are the conv2d operation configuration parameters:

* `dtype = ttnn.bfloat16` input activations data type.
* `weights_dtype = ttnn.bfloat16` weights and bias data type.
* `activation = ""` _optional_ `string`. Any activation function to apply. Options are `"relu"`.
* `input_channels_alignment = 32` _optional_ `uint32_t`. Alignment value for channels dimension in the input tensor. This is applicable when `in_channels < 32` and should take a value of `16` in those cases, `32` otherwise.
* `deallocate_activation = False` _optional_ bool indicating whether the input activation tensor memory should be deallocated.
* `reallocate_halo_output = False` _optional_ bool indicating if the intermediate tensor generated within the op should be reallocated to reduce memory fragmentation.
* `act_block_h_override = 0` _optional_ `uint32_t` to override the `act_block_h` parameter, which determines the size of blocks used in computations -- smaller values require less memory, larger values require more memory but are more performant. This argument is ignored when `shard_layout = WIDTH_SHARDED`.
* `act_block_w_div = 1` _optional_ `uint32_t`, value by which the maximum possible `act_block_w` parameter is divided. This arguments is ignored when `shard_layout = HEIGHT_SHARDED` or `BLOCK_SHARDED`.
* `reshard_if_not_optimal = False` _optional_ bool indicating whether the operation can re-shard the input tensor to make it more optimal for performance. If true, override_sharding_config should not be set to true.
* `override_sharding_config = False` _optional_ bool indicating if input sharding config should be overridden with provided shard_layout. If true, reshard_if_not_optimal should not be set to true.
* `shard_layout = None` _optional_ `ttnn.TensorMemoryLayout` to specify type of sharding to use.
* `core_grid = None` _optional_ `ttnn.CoreRangeSet` specifies the core grid to use. Applicable only when `override_sharding_config = True`,
* `transpose_shards = True` _optional_ `bool` whether the shards be distributed in `ROW_MAJOR` order. This is applicable only when not using height sharding.
* `output_layout = ttnn.TILE_LAYOUT` _optional_ `ttnn.Layout` to specify whether the output tensor be in `TILE` or `ROW_MAJOR` layout.
* `enable_act_double_buffer = False` _optional_ bool to enable activation double buffering.
* `enable_weights_double_buffer = False` _optional_ bool to enable weights double buffering when using block sharding.
* `enable_split_reader = False` _optional_ bool to two concurrent reader kernels instead of one.

#### Compute Config

Architecture specific device compute kernel configuration, `DeviceComputeKernelConfig` with the following parameters:

* `math_fidelity = MathFidelity.HiFi4`
* `math_approx_mode = True`
* `dst_full_sync_en = False`

Wormhole and Blackhole specific parameters:

* `fp32_dest_acc_en = False` enable accumulations in fp32.
* `packer_l1_acc = False` enable packer accumulation directly in L1.

#### Example Usage

##### Preparing input tensors

`conv2d` takes 4D `input_tensor` with dimensions ordered as `(N, H, W, C)` (channels last), and `weight_tensor` as `(C_in, C_out // groups, kernel_h, kernel_w)` 4D tensor. The input activation, weight and bias tensors can be on host or on device. If weight and bias are on device, they need to be already pre-processed by the conv2d op.

```python
    import ttnn
    import torch

    ## activation tensor

    input_shape_nchw = [batch_size, in_channels, input_height, input_width]
    torch_input_tensor_nchw = torch.randn(input_shape_nchw, dtype=torch.bfloat16)
    torch_input_tensor_nhwc = torch.permute(torch_input_tensor_nchw, (0, 2, 3, 1))

    ttnn_input_tensor = ttnn.from_torch(torch_input_tensor_nhwc, ttnn.bfloat16)

    ## weight tensor

    weight_shape = [out_channels, in_channels // groups, kernel_height, kernel_width]
    torch_weight_tensor = torch.randn(weight_shape, dtype=torch.bfloat16)

    ttnn_weight_tensor = ttnn.from_torch(torch_weight_tensor, ttnn.bfloat16)

    ## bias tensor

    bias_shape = [1, 1, 1, out_channels]
    torch_bias_tensor = torch.randn(conv_bias_shape, dtype=torch.bfloat16)

    ttnn_bias_tensor = ttnn.from_torch(torch_bias_tensor, ttnn.bfloat16)
```

##### Calling the operation

Once the inputs are prepared, we can call the `conv2d` operation as shown in the following example. Many of the arguments in the `conv2d` API are optional, and will be using defaults as listed above.

```python

    conv_config = ttnn.Conv2dConfig(
        dtype=ttnn.bfloat16,
        weights_dtype=ttnn.bfloat16
    )

    [ttnn_output_tensor_on_device, [out_height, out_width]] = ttnn.conv2d(
        input_tensor=ttnn_input_tensor,
        weight_tensor=ttnn_weight_tensor,
        in_channels=in_channels,
        out_channels=out_channels,
        device=device,
        bias_tensor=ttnn_bias_tensor,
        kernel_size=(kernel_h, kernel_w),
        stride=(stride_h, stride_w),
        padding=(pad_h, pad_w),
        dilation=(dilation_h, dilation_w),
        batch_size=batch_size,
        input_height=input_height,
        input_width=input_width,
        conv_config=conv_config,
        return_output_dim=True,
    )
```

Note that the `conv2d` supports controling the return of output dimensions, through argument `return_output_dim`, and for processed weights and bias tensors, through argument `return_weights_and_bias`.

To achieve higher performance it is advisable to use the following optional arguments:

* `deallocate_activation = True` If the input tensor is no longer needed after the conv2d operation, this option will free up the input buffer and have more memory available for the operation.
* `reallocate_halo_output = True` The `conv2d` operation executes a _haloing_ step before computing the convolutions to optimize memory accesses. This option will reallocate the output of this step in order to reduce memory fragmentation to avoid memory fitting issues.
* `enable_act_double_buffer = True` If enough memory is available, enabling double buffering of the input activations will result in a better performance.
* `enable_weights_double_buffer = false` If enough memory is available, enabling weights double buffering can improve performance when using block sharding.
* `enable_split_reader = True` By default, a single reader kernel is used to read in activations from the input shard. Enabling this option will use two concurrent reader kernels, potentially improving overall performance.

##### Output post-processing

The generated output of the `conv2d` operation is a 4D tensor with the `NHWC` order of dimensions, and requires a permute operation to convert to the standard `NCHW` order. The following is an example of how to typically post-process the output tensor. Note that the `reshape` is used to un-flatten the outout tensor. The slice operation removes any padding that may have been added by the operation to the last dimension.

```python
    ttnn_output_tensor = ttnn.from_device(ttnn_output_tensor_on_device)
    torch_output_tensor = ttnn.to_torch(ttnn_output_tensor)
    torch_output_tensor = torch_output_tensor.reshape(batch_size, out_height, out_width, torch_output_tensor.shape[-1])
    torch_output_tensor = torch_output_tensor[:, :, :, :out_channels]
    torch_output_tensor = torch.permute(torch_output_tensor, (0, 3, 1, 2))
```


### `maxpool2d`
_Coming soon._



Convolution as Matrix Multiplication
------------------------------------

Consider an example input image of resolution (dimensions) $16\times16$,
that is, height and width, $H$ and $W$ are both $16$, and each pixel has
a channel depth, $C$, of $32$ (see
Figure [\[fig:input\]](#fig:input){reference-type="ref"
reference="fig:input"}). Let us input two such images, setting batch
$N=2$, to the convolution operation. Putting it together, the input
tensor to convolution operation is, hence, of dimensions $[2,16,16,32]$,
where the order of the dimensions is $[N, H, W, C]$. Let us perform the
convolution with filters of size $[3,3]$ (see
Figure [\[fig:filters\]](#fig:filters){reference-type="ref"
reference="fig:filters"}), using a stride of $2$ in both $H$ and $W$
dimensions, indicating downsample, and with padding enabled. The output
of this convolution would be a tensor of dimensions $[2,8,8,32]$.

The key variables as input to the convolution operation are:

  -------------------- ----------- ------------ ------------ ------------
            **Input**:   $N = 2$    $H_i = 16$   $W_i = 16$   $C_i = 32$

    **Kernel window**:  $K_h = 3$   $K_w = 3$

           **Stride**:  $S_h = 2$   $S_w = 2$

           **Output**:   $N = 2$    $H_o = 8$    $W_o = 8$    $C_o = 32$
  -------------------- ----------- ------------ ------------ ------------

The input tensor to the convolution must first be transformed into a
matrix such that multiplying this matrix with the filters (as weights)
gives the convolution output -- In a convolution a dot product is
performed between the filter elements and each of the kernel window
position. This kernel window is a sliding window, going across the width
and height of the input image (see
Figure [\[fig:filterwindow\]](#fig:filterwindow){reference-type="ref"
reference="fig:filterwindow"}.) In a matrix multiply a dot product is
performed between a row in the first input and a column in the second
input. The transformed matrix must, hence, consist of rows where each
row corresponds to the elements from the input image that are overlapped
by the kernel window. This is illustrated in
Figure [\[fig:inputtransform\]](#fig:inputtransform){reference-type="ref"
reference="fig:inputtransform"}. For every valid kernel window position
(which corresponds to a unique output element), there must be a
corresponding row in the transformed matrix.

The filters can be reshaped into a matrix of dimensions
$[K_h \times K_w \times C_i, C_o]$. Based on this, the transformed input
tensor matrix should have dimensions
$[N \times H_o \times W_o , K_h \times K_w \times C_i]$. On multiplying
this matrix with the filters matrix (weight matrix) yields an output
matrix of dimensions $[N \times H_o \times W_o, C_o]$, which is the
expected output (see
Figure [\[fig:output\]](#fig:output){reference-type="ref"
reference="fig:output"}.)


Convolution Operation on Tenstorrent Architecture
=================================================

Implementation of Convolution Operation on a Single Tensix Core
---------------------------------------------------------------

In the implementation on a single Tensix core, we make the following
assumptions:

1.  The input and output activation tensors are stored across the global
    memory, either DRAM or L1, as interleaved buffers.

2.  The weights and bias tensors are stored in DRAM as an interleaved
    buffer.

3.  The local L1 memory size of the Tensix core is not big enough to
    store the entire input or output activation tensors.

The on-core L1 memory is used for the following:

-   Program binaries for the five RISC-V cores within a Tensix core.

-   Inputs to feed the compute core (partial activation and weights.)

-   Outputs from the compute core (partial intermediate and final
    results.)

A Tensix core has limited amount of L1 memory, which is about 1 MB on
Grayskull, and 1.5 MB on Wormhole architectures. For most applications,
this limited L1 memory is insufficient to store all of the input data.
Consequently, a portion of the input must be transferred into the local
L1 memory to perform computations to generate a corresponding portion of
the output. This partial output may need to be subsequently moved to the
global memory. This process is iterated until the complete output has
been computed. The partitioning of the inputs and the sequence of
transfers to the local memory must be meticulously managed to minimize
accesses to the global DRAM memory or remote L1 memory, which are
significantly slower than accesses to the local L1 memory, and maximize
the re-use of loaded input data into local L1 memory.

The input and output matrices are partitioned into *blocks*, the size of
which would be dictated by the maximum data size that can be
accommodated within the local L1 memory to perform corresponding partial
computations. For a specified output block, the sizes of the
corresponding input activation and weight blocks can be determined as in
the following.

In order to compute an output block of dimensions $[bH_{o}, bW_{o}]$, we
need the the following input blocks:

1.  an activation matrix of dimensions
    $[bH_{o}\textbf{,} \ K_h \times K_w \times C_i]$

2.  weights matrix of dimension $[K_h \times K_w \times C_i, bW_{o}]$

To make sure that the output block and corresponding input data fit in
local L1, the following constraints must be met.

-   $[bH_{o}\times bW_{o} + K_h \times K_w \times C_i \times (bH_{o} + bW_{o})] \times \texttt{sizeof}($datatype$) < L1_{free}$

-   $bH_{o} \bmod 32 = 0$

Additionally, the compute unit in a Tensix core can process up to eight
output tiles at once. Thus, if the output block is greater than total of
8 tiles in size, it must be further subdivided into *sub-blocks*.

Given this context, the convolution implementation can be described as
the following algorithm.

1.  Transform the input tensor into the activation matrix.

2.  [\[alg:firstload\]]{#alg:firstload label="alg:firstload"} Load a
    block of activation and corresponding weights from in to the local
    L1 memory.

3.  Compute one output block and write it to the output global memory.

4.  Load the next activation block, reusing the same weights block by
    moving to the next blocks along the height of the input matrix.

5.  Compute corresponding output and write it to the output global
    memory.

6.  [\[alg:inner\]]{#alg:inner label="alg:inner"} Repeat the above
    process until an entire column of the output blocks has been
    computed.

7.  Repeat steps
    [\[alg:firstload\]](#alg:firstload){reference-type="ref"
    reference="alg:firstload"}-[\[alg:inner\]](#alg:inner){reference-type="ref"
    reference="alg:inner"} for each column of blocks in the matrixm
    until the entire output is calculated.

Activation Input Layout Transformation
--------------------------------------

The activation input to the convolution operation is a tensor with the
shape: $[N, C, H, W]$. On the host, the tensor is permuted to make the
channels the inner most dimension, to $[N, H, W, C]$. This tensor is
loaded into the device global DRAM memory.

Weight and Bias tensor Layout Transformation
--------------------------------------------

The weight tensors are permuted to the following order
$[K_h, K_w, C_i, C_o]$ such that the output channels dimension $C_o$ is
the fastest moving dimension. It is then flattened into two dimensional
matrix of size $[K_h\times K_w \times C_i , C_o]$. If needed, two
dimensions of this weight matrix are padded to be multiplies of tile
size.

The bias tensor, which is essentially a vector of length $C_o$, is
converted into a two dimensional matrix of dimension $[32, C_o]$ by
padding with zeros, where 32 is the tile width. All these operations are
carried out on the host before moving the data to the device.

Convolution Kernels on a Single Tensix Core
-------------------------------------------

Within a Tensix core, each of the five RISC-V cores are programmed
through kernel code, where each receives code compiled for its specific
role in the operation. Two of these cores perform the data movement,
while the remaining three are compute cores. There are two data movement
kernels, one for each of the data movement cores -- one of these reads
activation input blocks from the global memory to local L1 memory, and
the other reads weights and biases from global memory to local L1 memory
(Step [\[alg:firstload\]](#alg:firstload){reference-type="ref"
reference="alg:firstload"}). Additionally, it writes the output from
local L1 memory to global memory.

One compute kernel is compiled into three separate programs that are run
on the three compute cores. These are the *unpack*, *math*, and *pack*
cores. These three cores work together to perform the computations on
data available in the local L1 memory, loaded by the first data movement
core. The unpack core loads up the source registers with the input data
block, the math core performs the matrix multiplication and bias add
operations on the data in these source registers, generating result
output block in to the destination registers. The pack core moves the
output block data from the destination registers to the local L1 memory.

<img src="media/op1.png" style="width:500px;">\
_Convolutions operation using generic interleaved global tensors._

<img src="media/op2.png" style="width:500px;">\
_Convolutions operation using sharded local tensors._

Parallelization of Convolution Operation
========================================

Interleaved Tensors
-------------------

Tenstorrent architectures support tensor interleaving as a setup for
optimizing convolution. By interleaving tensors, the amount of hardware
that is used to access consecutive data is maximized, allowing for
further parallelization.

On the Tenstorrent architectures, we have a number of memory banks
dependent on the type of chip. Interleaved tensors store the data pages
in an round-robin fashion across these banks. Any of the Tensix cores
can access any of the data pages for such tensors. We use this tensor
parallelization format to develop a simple, non-performant version of
the convolution operation.

Sharding
--------

To develop a high-performance implementation of convolution operations
on the Tenstorrent architectures, we start with *sharding* the input
activation tensor, so that each core is the owner of a distinct
contiguous chunk of the input data stored in its local L1 memory.
Performing computations on the data owned by a core would mostly use the
data already present locally, and would reduce the inter-core data
accesses, optimizing these access patterns. In a later section, we will
describe how we completely eliminate all remote data accesses during the
convolution operation through haloing.

Convolutions on Tenstorrent architectures support three sharding
strategies: *height*, *width*, and *block*. To demonstrate the mechanics
of each strategy, consider a 2D matrix of size $[H, W]$ (representing a
flattened tensor), and let $p$ be the number of cores used.

<img src="media/heightshard.png" style="width:300px;">\
<img src="media/blockshard.png" style="width:300px;">

1.  **Height sharding (1D)**: In the height sharded scheme, the input
    matrix height is equally divided into $p$ contiguous segments and
    width is kept as full, and each segment is assigned to a different
    core. Hence, each resulting shard will have a height of $H / p$ and
    width of $W$.

2.  **Width sharding (1D)**: In the width sharded scheme, the input
    matrix width is equally divided into $p$ segments, while the height
    is kept as full, and each core is assigned a different segment. Each
    resulting shard will be of height $H$ and width of $W / p$.

3.  **Block sharding (2D)**: Block sharding scheme involves equally
    dividing both height and width into a total of $p$ submatrices. Let
    the core grid be of size $m \times n$, where $p = m*n$. Then each
    resulting shard will have a height of $H / m$ and width of $W / n$.

Sharding of the input activations to the convolution operation could use
any of these schemes. Once the shards are loaded in to the L1 memory,
each Tensix core performs convolutions on the segment of data it is
assigned. This may also involve moving data across cores. For the height
sharding case, we do not need any inter-core data movements since we
replicate the weights tensor across all participating cores. In block
sharding, since each core is assigned a slice of the tensor, which would
only generate partial results, we use the multicast operation to move
the activation block data a core needs. We describe this next.

Sharded Input Data Movement Across Cores
----------------------------------------

Computing a single output value requires a full row of the activation
matrix and a full column of the weights matrix. In Height Sharding, all
cores possess full rows of the input, enabling them to independently
calculate their assigned outputs. Block Sharding and Width Sharding
divide the input along the channels dimension. Consequently, no single
core has all the necessary input to compute a complete output value.
Cores must share input data to compute full outputs. Data sharing occurs
only along the input width dimensions. In Width Sharding, each core
shares its input data with every other core. In Block Sharding, only
cores in the same row share data with each other. The computation
process follows several steps.

1.  First, each core fetches a subset of the weights matrix
    corresponding to its assigned output.

2.  Then, each core computes a partial output using its local input
    data.

3.  The first core broadcasts its input to all cores that need it.

4.  Receiving cores calculate another partial output and add it to the
    existing one.

5.  This process repeats with each core broadcasting its input in turn.

6.  After all cores have broadcasted their input, final outputs are
    calculated.

7.  This approach allows for efficient parallel processing while
    ensuring all necessary data is shared among cores to produce
    accurate final outputs.

Haloing
-------

<img src="media/halos.png" style="width:200px;">\
_Halo._

In the following example, we describe the haloing process. This is a
data movement operation we use to construct \"haloed\" shards, where
each input shard contains all the data it requires to generate
convolution output for its assigned output tensor shard. This eliminates
any need for a Tensix core to access the L1 memory of another core
during the convolution operation.

To demonstrate this process of constructing haloed shards, let's start
off with an example. We start with the following tensors:

1.  Input activation tensor of size $[1, 6, 4, 6]$.

2.  Weight tensor of size $[6, 6, 3, 3]$.

3.  Output activation tensor of size $[1, 6, 4, 6]$.

This tensor can be visualized as in the following
Figure [6](#fig:halo1){reference-type="ref" reference="fig:halo1"}. We
will separate the input tensor dimensions versus the output tensor
dimensions.

<img src="media/halo1.png" style="width:200px;">

For simplicity, let the batch size be one. IN the figure, we also
demonstrate a single channel view of this block. This view will be a
useful visualization tool on which we will build on top of. Let us
assume we have $p = 3$ cores. The sharding strategy we will be using is
*height*-sharding. This is depicted in the figure via three distinct
colors, one for each shard.

<img src="media/halo2.png" style="width:200px;">

Next, we can visualize what our window will look like. Recall that the
weight tensor consists of a number of filters, and each filter consists
of one or more kernels. This kernel is also referred to as the *window*
in 2D visualization representation. We can see the 3D kernels (a single
filter) that is being convoluted across our input tensor.

<img src="media/halo3.png" style="width:200px;">

We will keep in mind the strides, $S_w$ and $S_h$, as how many data
elements we traverse by. We have not shown any padding ($pad_h$ and
$pad_w$), but they will also be included if they were non zero values.
The 2D representation shows the window and what parts of each shard it
will perform matrix multiplication with. We can see that the shown
window position spans two different shards. Thus, if we were calculating
the output data element for this window, we would somehow need to get
some shard data from another core.

In the following figure, we see the same window that has traversed
several elements and is located at its current position. In the 2D
single channel representation, we can see that this window spans data
from all 3 shards. Thus, for this particular output data element, it
will need data from its current core, as well as 2 other cores for the 2
other shards.

<img src="media/halo4.png" style="width:200px;">

<img src="media/halo5.png" style="width:200px;">

The goal of halo is to figure out what data is needed for the current
output data element calculation, and to bring that within the core that
is doing the computation. We will stick to the case where we only need
to gather data from another shard. Assume the same example tensor as
before with the same weight/filter/kernel parameters. From the previous
example, we will first add the appropriate padding onto the input
tensor. In the case of convolution, the padding value is 0. We have
chosen to have $pad_w$ and $pad_h$ to be 0.

<img src="media/halo6.png" style="width:200px;">

Moving on, from this tensor, we will generate another tensor of boolean
values that will be sized the same as the original input tensor. Each of
these values will signify whether the current element is a padding value
or a data value. Padding values are set to true (value=1), while the
latter is set to false (value=0). This is called our padding config
tensor.

<img src="media/halo7.png" style="width:200px;">

Next up, we will traverse through the input tensor and store the indices
that correspond to each stick. You can see that certain sticks will
correspond to padding values whereas certain sticks will correspond to
data values. We store these indices. If you know the top-leftmost index,
you can generate all the indices in your window that you will need.

<img src="media/halo8.png" style="width:200px;">

Now we will determine where data needs to be read from. We first compute
what part of the output each core is responsible for. Therefore, the
point of view of computation is from the output, not the input. Our
output tensor dimensions are as shown. Each shard will be computed by a
specific core. Let us focus on the first shard. Going back to our input,
we can traverse through each output data element and figure out what
input elements were needed to compute that. The 2D window diagrams you
see are the window being convoluted across the input sticks to get the
entirety of the blue shard output. When doing this traversal, we can
store the indices that we need to obtain in the current core. There are
3 types: padding config, local config and remote config. Padding config
refers to the indices that are padding sticks. Local config refers to
the indices that are already present in the current core. Remote config
refers to the indices that need to be obtained from another core.

As you can see, the blue shard output needs to get the input indices as
below: padding: \[1, 2, 3, 4, 5, 6, 7, 8, 9, 16, 17, 24, 25\] local:
\[10, 11, 12, 13, 14, 15, 18, 19\] remote: \[20, 21, 22, 23, 26, 27,
28\]

At this point, the local core which will compute the blue shard output
knows what data it needs to get and where. Thus, it will issue a Halo
operation with these indices and their locations and obtain the relevant
data within its own core.

<img src="media/halo9.png" style="width:200px;">\
<img src="media/halo10.png" style="width:200px;">


CNN Models: ResNet-50 Benchmark
===============================

<img src="media/resnet1.png" style="width:200px;">\
<img src="media/resnet2.png" style="width:200px;">\
_Resnet Blocks_

ResNet-50 is a CNN with 50 layers, part of
the ResNet (Residual Network) family. Primarily to address the vanishing
gradient problem associated with training deep neural networks, ResNet
was introduced. ResNet-50 utilises a concept called residual learning,
which helps in training deeper networks more effectively. From an
inference perspective, Resnet-50 is efficient and effective in making
predictions on new data once it is trained.

Following is simplified diagram and description of ResNet block

ReLU Activation: The Rectified Linear Unit(ReLU) activation function is
applied after each convolution layer and batch normalisation layers. It
filters positive values and in turn introduces non-linearity into the
network, which is needed for the network to learn complex patterns in
data. Bottleneck Convolution Layers: This block consists of three
convolutional layers with batch normalization and ReLU activation after
each.:

1x1 convolution: This layer is used to reduce the number of channels in
input data. By reducing dimensionality, the data is compressed and
higher computational efficiency is achieved without affecting
information.

3x3 convolution: This is the core convolution layer which extracts
special features of the data.

1x1 convolution: It restores original number of channels to add in
original input using skip connection.

Skip Connection: It adds input of the bottleneck convolution layer to
output of it. This bypass connection makes sure that essential
information from previous layers is passed through the network. While
training this helps to resolve vanishing gradient issues and speeds up
training. On the other hand, while inferencing it helps in maintaining
smooth flow of gradients and features, which in turn helps in prediction
accuracy.

Summery From a training perspective, ResNet-50's architecture
effectively leverages residual learning with its ResNet blocks to enable
training of deep neural networks. The residual blocks, with their use of
1x1 and 3x3 convolutions, along with shortcut connections, help in
efficiently learning complex patterns and gradients, which improves the
network's performance and training stability.

From an inference perspective, ResNet-50 is efficient and effective due
to its use of residual blocks and shortcut connections. These elements
allow the network to make predictions quickly and accurately by
leveraging deep feature extraction while maintaining manageable
computational complexity. The residual blocks, through their combination
of convolutions and shortcut connections, ensure robust learning and
performance during inference.

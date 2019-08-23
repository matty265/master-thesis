from deephar.layers import Softargmax
from datasets import MPIIDataset, mpii_joint_order
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import multivariate_normal
from deephar.utils import transform_pose
from deephar.utils import linspace_2d as my_linspace_2d

from skimage import io
import torch

import tensorflow as tf

from keras.models import Model
from keras import backend as K
from keras.layers import SeparableConv2D
from keras.layers import Lambda
from keras.layers import Activation
from keras.layers import concatenate
from keras.layers import Input

configurations = [
    ((43, 60), 1),
    ((43, 60), 2),
    ((43, 60), 10),
    ((43, 60), 20),
    ((64, 64), 1),
    ((64, 64), 2),
    ((64, 64), 10),
    ((64, 64), 20),
    ((64, 64), 100),
    ((120, 120), 20),
    ((30, 10), 20),
]

def linspace_2d(nb_rols, nb_cols, dim=0):

    def _lin_sp_aux(size, nb_repeat, start, end):
        linsp = np.linspace(start, end, num=size)
        x = np.empty((nb_repeat, size), dtype=np.float32)

        for d in range(nb_repeat):
            x[d] = linsp

        return x

    if dim == 1:
        return (_lin_sp_aux(nb_rols, nb_cols, 0.0, 1.0)).T
    return _lin_sp_aux(nb_cols, nb_rols, 0.0, 1.0)

def lin_interpolation_2d(inp, dim):

    num_rows, num_cols, num_filters = K.int_shape(inp)[1:]
    conv = SeparableConv2D(num_filters, (num_rows, num_cols), use_bias=False)
    x = conv(inp)

    w = conv.get_weights()
    w[0].fill(0)
    w[1].fill(0)
    linspace = linspace_2d(num_rows, num_cols, dim=dim)
    #print("luvizon: dim {} linspace-shape {}".format(dim, linspace.shape))

    for i in range(num_filters):
        w[0][:,:, i, 0] = linspace[:,:]
        w[1][0, 0, i, i] = 1.

    #print("luv", dim, w[0][:, 0, :, :])

    conv.set_weights(w)
    conv.trainable = False

    # shape: ? 1 1 16
    x = Lambda(lambda x: K.squeeze(x, axis=1))(x)
    x = Lambda(lambda x: K.squeeze(x, axis=1))(x)
    # shape: ? 16
    x = Lambda(lambda x: K.expand_dims(x, axis=-1))(x)
    # shape: ? 16 1
    return x

def act_channel_softmax(x, name=None):
    x = Activation(channel_softmax_2d(), name=name)(x)
    return x

def channel_softmax_2d():

    def _channel_softmax_2d(x):
        ndim = K.ndim(x)
        if ndim == 4:
            maximum = K.max(x, axis=(1,2), keepdims=True)
            #print("max shape", maximum.shape)
            e = K.exp(x - maximum)
            #print("exp shape", e.shape)
            s = K.sum(e, axis=(1,2), keepdims=True)
            #print("sum shape", s.shape)
            return e / s
        else:
            raise ValueError('This function is specific for 4D tensors. '
                    'Here, ndim=' + str(ndim))

    return _channel_softmax_2d

def build_softargmax_2d(input_shape, rho=0., name=None):

    if name is None:
        name_sm = None
    else:
        name_sm = name + '_softmax'

    # shape: height, width, channel
    #        480, 640, 1
    inp = Input(shape=input_shape)
    #x = act_channel_softmax(inp, name=name_sm)

    x_x = lin_interpolation_2d(inp, dim=0)
    x_y = lin_interpolation_2d(inp, dim=1)
    x = concatenate([x_x, x_y])

    model = Model(inputs=inp, outputs=x, name=name)
    model.trainable = False

    return model

def create_2d_normal_image(mean, cov, width, height):
    kernel = multivariate_normal(mean=mean, cov=np.eye(2)*cov)

    xlim = (0, width)
    ylim = (0, height)
    xres = width
    yres = height
    x = np.linspace(xlim[0], xlim[1], xres)
    y = np.linspace(ylim[0], ylim[1], yres)
    xx, yy = np.meshgrid(x,y)

    xxyy = np.c_[xx.ravel(), yy.ravel()]
    zz = kernel.pdf(xxyy)

    img = zz.reshape((yres,xres))
    return img

def print_matrices(matrices):
    numeric_matrices = matrices.astype('uint8')

    for i in range(len(variances)):
        plt.subplot(230 + i + 1)
        plt.imshow(matrices[i])
        plt.title("variance " + str(variances[i]))

    plt.savefig("test.png")
    plt.show()

def test_config(mean, cov, width, height):
    model = Softargmax(kernel_size=(width, height), input_filters=1, output_filters=1)

    heatmap = create_2d_normal_image(mean, cov, width, height)

    x = mean[0]
    y = mean[1]

    heatmap_torch = heatmap.reshape(1, 1, height, width)
    output = model(torch.from_numpy(heatmap_torch).float())
    #heatmap = np.expand_dims(heatmap, axis=0)

    tf_heatmap = heatmap.reshape(height, width, 1)
    original_model = build_softargmax_2d(tf_heatmap.shape)
    output_original = original_model.predict(tf_heatmap.reshape(1, height, width, 1))

    [scale_x, scale_y] = output.numpy()[0][0]
    pred_x, pred_y = int(scale_x * width), int(scale_y * height)

    diff_x = abs(pred_x - x)
    diff_y = abs(pred_y - y)

    tf_scaled = (output_original * np.array([width, height]))[0][0]
    tf_pred_x = int(tf_scaled[0])
    tf_diff_x = abs(pred_x - x)

    tf_pred_y = int(tf_scaled[1])
    tf_diff_y = abs(pred_y - y)

    return [ [pred_x, diff_x, pred_y, diff_y], [ tf_pred_x, tf_diff_x, tf_pred_y, tf_diff_y ], heatmap]

def main():
    #variances = [1, 2, 5, 10, 20, 50]
    variances = [1]

    ds = MPIIDataset("/data/mjakobs/data/mpii/", use_saved_tensors=True)

    example = ds[1000]
    
    '''
    image_number = "{}".format(int(example["image_path"][0].item()))
    image_name = "{}.jpg".format(image_number.zfill(9))
    
    original_image = io.imread("/data/mjakobs/data/mpii/images/{}".format(image_name))
    original_pose = example["normalized_pose"][:, 0:2]

    orig_gt_coordinates = transform_pose(example["trans_matrix"], original_pose, inverse=True)

    '''
    original_image = example["normalized_image"].reshape(256, 256, 3)
    orig_gt_coordinates = example["original_pose"] * 256.0

    height, width = original_image.shape[0], original_image.shape[1]
    print(width, height)

    plt.figure()
    for i, pose in enumerate(orig_gt_coordinates):
        x = int(pose[0])
        y = int(pose[1])

        plt.subplot(4, 4, 1 + i)
        output = test_config((x,y), 20, width, height)
        my_output = output[0]
        tf_output = output[1]

        print("{}: predicted ({} {}), gt ({} {})".format(mpii_joint_order[i], my_output[0], my_output[2], x, y))
        print("luvizon: predicted ({} {}), gt ({} {}".format(tf_output[0], tf_output[2], x , y))
        print()
        heatmap = output[-1]
        plt.xticks([])
        plt.yticks([])
        plt.imshow(original_image)
        plt.imshow(heatmap, alpha=0.5)
        plt.scatter(x=my_output[0], y=my_output[2], facecolors='none', edgecolors='#FF00FF')
        plt.scatter(x=tf_output[0], y=tf_output[2], facecolors='none', edgecolors='r')
        plt.title(mpii_joint_order[i])

    plt.show()

        

    #for (mean, cov) in configurations:
    #    print(test_config(mean, cov))

    # results = np.empty((len(variances), 128, 128))

    # #for i, scale in enumerate([1, 2, 5, 10, 20, 50]):
    # for i, scale in enumerate(variances):
    #     for x in range(128):
    #         for y in range(128):
    #             result = test_config((x, y), np.eye(2)*scale)
    #             print(x, result[0], y, result[1])
    #             results[i][x][y] = result[2]

    # print(results)
    # print_matrices(results)

main()
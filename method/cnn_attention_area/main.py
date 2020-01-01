'''
1) get the attention area by VAE model
2) model cnn part is x-ception (, maybe)
'''
import argparse
import os
import pprint
import random
import sys

import cv2
import numpy as np
import pandas as pd
import torch
import torch.utils.data
from torch import nn, optim
from torch.nn import functional as F
from torchvision import datasets, transforms
from torchvision.utils import save_image

# append sys.path
sys.path.append(os.getcwd())
from pre_processing.utility import get_coordinate, get_image_info
from utility.auto_encoding_variational import VAE


# define argument
def argument():
    parser = argparse.ArgumentParser()
    parser.add_argument('--path-input', default=None)
    parser.add_argument('--path-model-vae', default=None)
    parser.add_argument('--dir-image', type=str)
    parser.add_argument('--size-cutting', default=32)

    parser.add_argument('--rate-train', default=0.9, type=float)
    parser.add_argument('--size-batch', type=int, default=128,
        help='input batch size for train (default: 128)')
    parser.add_argument('--epoch', type=int, default=10,
        help='number of epoch to train (default: 10)')

    parser.add_argument('--no-cuda', action='store_true', default=False,
        help='enables CUDA train')
    parser.add_argument('--seed', type=int, default=1,
        help='random seed (default: 1)')

    parser.add_argument('--num-cross', default=None, type=int)
    parser.add_argument('--use-cross', default=None, type=int)

    parser.add_argument('--no-attention-area', action='store_true', default=False)

    args = parser.parse_args()
    cuda = not args.no_cuda and torch.cuda.is_available()

    random.seed(args.seed)
    device = torch.device("cuda" if cuda else "cpu")
    args.device = device
    return args

# define data set
class DatasetTrain():
    def __init__(self, list_data_set):
        self.list_data_set = list_data_set

    def __len__(self):
        return len(self.list_data_set)

    def __getitem__(self, idx):
        image_current = self.list_data_set[idx]
        image_coordinate = get_coordinate(image_current)

        # get image path
        name_subset = os.path.basename(
            os.path.dirname(image_current['path_seriesuid_folder'])
            ).split('_')[0] + '_tiff'
        image_index = int(image_coordinate['coordinate_z'])

        path_image = os.path.join(
            args.dir_image,
            name_subset,
            image_current['seriesuid'],
            'whole_image',
            'whole_{image_index}.tiff'.format(image_index=image_index)
            )
        image = cv2.imread(path_image, flags=2)
        image = image / 255

        # cut the image
        x_start = int(image_coordinate['coordinate_x'] - args.size_cutting / 2)
        x_end = int(image_coordinate['coordinate_x'] + args.size_cutting / 2)
        y_start = int(image_coordinate['coordinate_y'] - args.size_cutting / 2)
        y_end = int(image_coordinate['coordinate_y'] + args.size_cutting / 2)

        image = image[x_start: x_end, y_start: y_end]
        image = cv2.resize(image, (50, 50))
        image = np.expand_dims(image, 0)

        # get the label
        label = int(image_current['class'])
        return image, label

class DatasetTest():
    def __init__(self, list_data_set):
        self.list_data_set = list_data_set

    def __len__(self):
        return len(self.list_data_set)

    def __getitem__(self, idx):
        image_current = self.list_data_set[idx]
        image_coordinate = get_coordinate(image_current)

        # get image path
        name_subset = os.path.basename(
            os.path.dirname(image_current['path_seriesuid_folder'])
            ).split('_')[0] + '_tiff'
        image_index = int(image_coordinate['coordinate_z'])

        path_image = os.path.join(
            args.dir_image,
            name_subset,
            image_current['seriesuid'],
            'whole_image',
            'whole_{image_index}.tiff'.format(image_index=image_index)
            )
        image = cv2.imread(path_image, flags=2)
        image = image / 255

        # cut the image
        x_start = int(image_coordinate['coordinate_x'] - args.size_cutting / 2)
        x_end = int(image_coordinate['coordinate_x'] + args.size_cutting / 2)
        y_start = int(image_coordinate['coordinate_y'] - args.size_cutting / 2)
        y_end = int(image_coordinate['coordinate_y'] + args.size_cutting / 2)

        image = image[x_start: x_end, y_start: y_end]
        image = cv2.resize(image, (50, 50))
        image = np.expand_dims(image, 0)
        return image

class CnnModel(nn.Module):
    def __init__(self, args):
        super().__init__()

        if args.no_attention_area:
            # input 1 * 50 * 50
            self.conv_1 = nn.Conv2d(
                in_channels=1, out_channels=20, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
            ) # 20 * 44 * 44

        else:
            # input 2 * 50 * 50
            self.conv_1 = nn.Conv2d(
                in_channels=2, out_channels=20, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
            ) # 20 * 44 * 44

        self.pooling_1 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 20 * 22 * 22

        self.conv_2 = nn.Conv2d(
            in_channels=20, out_channels=50, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 50 * 16 * 16

        self.pooling_2 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 50 * 8 * 8

        self.conv_3 = nn.Conv2d(
            in_channels=50, out_channels=500, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 500 * 2 * 2

        self.pooling_3 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 500 * 1 * 1

        # activate fuction ReLU layer

        self.conv_4 = nn.Conv2d(
            in_channels=500, out_channels=2, kernel_size=1, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 2 * 1 * 1

        '''
        # original model
        # input 1* 50 * 50

        self.conv_1 = nn.Conv2d(
            in_channels=1, out_channels=20, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 20 * 44 * 44

        self.pooling_1 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 20 * 22 * 22

        self.conv_2 = nn.Conv2d(
            in_channels=20, out_channels=50, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 50 * 16 * 16

        self.pooling_2 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 50 * 8 * 8

        self.conv_3 = nn.Conv2d(
            in_channels=50, out_channels=500, kernel_size=7, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 500 * 2 * 2

        self.pooling_3 = nn.MaxPool2d(
            kernel_size=2, stride=2, padding=0, dilation=1, return_indices=False, ceil_mode=False
        ) # 500 * 1 * 1

        # activate fuction ReLU layer

        self.conv_4 = nn.Conv2d(
            in_channels=500, out_channels=2, kernel_size=1, stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros'
        ) # 2 * 1 * 1
        '''

    def forward(self, input_image):
        out = self.conv_1(input_image) # 20 * 44 * 44
        out = self.pooling_1(out) # 20 * 22 * 22

        out = self.conv_2(out) # 50 * 16 * 16
        out = self.pooling_2(out) # 50 * 8 * 8

        out = self.conv_3(out) # 500 * 2 * 2
        out = self.pooling_3(out) # 500 * 1 * 1

        out_relu = F.relu(out)

        # out = F.dropout(out_relu)
        out = self.conv_4(out) # 2 * 1 * 1

        return out

def get_data_attentioned(data, attention_area):
    return data + attention_area # 并列不同的维度， 不进行算数叠加

def loss_function(prediction, label):
    pass

def train(model, optimizer, model_vae, train_loader, epoch, args):

    model.train()
    train_loss = 0
    for batch_idx, (data, label) in enumerate(train_loader):
        data = data.to(args.device, dtype= torch.float)

        # train the model
        optimizer.zero_grad()

        if not args.no_attention_area:

            # get attention area
            attention_area = model_vae(data)
            data_attentioned = get_data_attentioned(data, attention_area)

            prediction = model(data_attentioned)

        else:
            prediction = model(data)

        loss = loss_function(prediction, label)
        loss.backward()
        train_loss += loss.item()
        optimizer.step()

        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader),
                loss.item() / len(data)))

    print('====> Epoch: {} Average loss: {:.4f}'.format(
          epoch, train_loss / len(train_loader.dataset)))

def test(model, optimizer, model_vae, test_loader, epoch, args):
    model.eval()
    test_loss = 0
    with torch.no_grad():
        for i, data in enumerate(test_loader):
            data = data.to(args.device, dtype= torch.float)

            # get attention area
            attention_area = model_vae(data)

            # test the model
            recon_batch, mu, logvar = model(data)
            test_loss += loss_function(recon_batch, data, mu, logvar, args).item()

            if i == 0:
                n = min(data.size(0), 8)
                comparison = torch.cat([data[:n],
                                      recon_batch.view(data.shape[0], 1, args.size_cutting, args.size_cutting)[:n]])

                sub_path_reconstruction = 'method/vae_bc_learning/results/reconstruction_' + str(epoch) + '.png'
                path_reconstruction = os.path.join(os.getcwd(), sub_path_reconstruction)
                save_image(
                    comparison.cpu(),
                    path_reconstruction,
                    nrow=n)

    test_loss /= len(test_loader.dataset)
    print('====> Test set loss: {:.4f}'.format(test_loss))

if __name__ == "__main__":
    # get argument
    args = argument()

    # get vae model
    if not args.no_attention_area:
        # get path of model vae
        path_model_vae = os.path.join(os.getcwd(), args.path_model_vae)

        # load model vae
        model_vae = VAE()
        model_vae.load_state_dict(torch.load(path_model_vae))
    else:
        model_vae = None

    # get image info
    info_luna16 = pd.read_csv(args.path_input, index_col=0)
    list_info_image = get_image_info(info_luna16)
    random.shuffle(list_info_image)

    if not(args.num_cross is None) and not (args.use_cross is None):
        # get train part and test part by cross number
        pass
    else:
        # get train part and test part by train rate
        len_list_train = int(len(list_info_image) * args.rate_train)
        list_train = list_info_image[: len_list_train]
        list_test = list_info_image[len_list_train: ]

    # define date loader
    data_set_train = DatasetTrain(list_train)
    data_set_test = DatasetTest(list_test)

    train_loader = torch.utils.data.DataLoader(
        data_set_train,
        batch_size=args.size_batch,
        shuffle=True,
        )
    test_loader = torch.utils.data.DataLoader(
        data_set_test,
        batch_size=args.size_batch,
        shuffle=True,
        )

    # model instance
    model = CnnModel(args).to(args.device)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)

    for epoch in range(1, args.epoch + 1):
        train(model, optimizer, model_vae, train_loader, epoch, args)
        test(model, optimizer, model_vae, test_loader, epoch, args)
        with torch.no_grad():
            sample = torch.randn(64, args.dimension_latent).to(args.device)
            sample = model.decode(sample).cpu()
            
            sub_path_sample = 'method/vae_bc_learning/results/sample_' + str(epoch) + '.png'
            path_sample = os.path.join(os.getcwd(), sub_path_sample)
            save_image(
                sample.view(64, 1, int(args.size_cutting), int(args.size_cutting)),
                path_sample)

import torch
import torch.utils.data as data

import os
import re
import glob

import scipy.io as sio
import numpy as np
import pandas as pd

from skimage import io
from skimage.transform import resize

from deephar.image_processing import center_crop, rotate_and_crop, normalize_channels
from deephar.utils import transform_2d_point, translate, scale, flip_h, superflatten, transform_pose, get_valid_joints

class PennActionDataset(data.Dataset):

    def __init__(self, root_dir, use_random_parameters=True, transform=None):
        self.root_dir = root_dir
        self.items = sorted(os.listdir(self.root_dir + "frames"))

        self.mpii_mapping = np.array([
            [0, 8],  # head -> upper neck
            [1, 13], # left shoulder
            [2, 12], # right shoulder
            [3, 14], # left elbow
            [4, 11], # right elbow
            [5, 15], # left wrist
            [6, 10], # right wrist
            [7, 3],  # left hip
            [8, 2],  # right hip
            [9, 4],  # left knee
            [10, 1], # right knee
            [11, 5], # left ankle
            [12, 0]  # right ankle
        ])

        self.action_mapping = {
            "baseball_pitch": 0,
            "baseball_swing": 2,
            "bench_press": 3,
            "bowling": 4,
            "clean_and_jerk": 5,
            "golf_swing": 6,
            "jumping_jacks": 7,
            "jump_rope": 8,
            "pull_ups": 9,
            "push_ups": 10,
            "sit_ups": 11,
            "squats": 12,
            "strumming_guitar": 13,
            "tennis_forehand": 14,
            "tennis_serve": 15
        }

        self.final_size=256

        if use_random_parameters:
            self.angles=np.array(range(-30, 30+1, 5))
            self.scales=np.array([0.7, 1.0, 1.3, 2.5])
            self.channel_power_exponent = 0.01*np.array(range(90, 110+1, 2))
            self.flip_horizontal = np.array([0, 1])
            self.trans_x=np.array(range(-40, 40+1, 5))[0],
            self.trans_y=np.array(range(-40, 40+1, 5))[0],
            self.subsampling=[1, 2]
        else:
            self.angles=np.array([0, 0, 0])
            self.scales=np.array([1., 1., 1.])
            self.flip_horizontal = np.array([0, 0])
            self.channel_power_exponent = None
            self.trans_x=np.array([0., 0., 0.]),
            self.trans_y=np.array([0., 0., 0.]),
            self.subsampling=[1, 1]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        label_path = self.root_dir + "labels/" + self.items[idx]
        label = sio.loadmat(label_path)
        images = []
        frame_folder = self.root_dir + "frames/" + self.items[idx] + "/"
        all_images = sorted(os.listdir(frame_folder))

        poses = []
        for i in range(len(all_images)):
            image = io.imread(frame_folder + all_images[i])
            images.append(image)

            joint_frame = []
            for o in range(13):
                joint_coordinate = [label["x"][i][o], label["y"][i][o]]
                joint_frame.append(joint_coordinate)

            poses.append(joint_frame)

        images, normalized_images, poses, trans_matrices = self.preprocess(np.array(images), np.array(poses))

        normalized_pose = poses.copy()
        normalized_pose[:, :,0:2] /= self.final_size

        action = label["action"][0]
        action_1h = np.zeros(16)
        action_1h[self.action_mapping[action]] = 1

        return {
            "action_label": action,
            "action": action_1h,
            "images": images,
            "poses": poses,
            "normalized_frames": normalized_images,
            "normalized_poses": normalized_pose,
            "trans_matrix": trans_matrices
        }

    def preprocess(self, images, poses):
        conf_scale = self.scales[np.random.randint(0, len(self.scales))]
        conf_angle = self.angles[np.random.randint(0, len(self.angles))]
        conf_flip = self.flip_horizontal[np.random.randint(0, len(self.flip_horizontal))]
        conf_subsample = self.subsampling[np.random.randint(0, len(self.subsampling))]
        conf_trans_x = self.trans_x[np.random.randint(0, len(self.trans_x))]
        conf_trans_y = self.trans_y[np.random.randint(0, len(self.trans_y))]

        if self.channel_power_exponent is not None:
            conf_exponents = np.array([
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))],
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))],
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))]
            ])
        else:
            conf_exponents = None

        image_width = images.shape[2]
        image_height = images.shape[1]
        window_size = conf_scale * max(image_height, image_width)

        bbox = np.array([
            max(int(image_width / 2) - (window_size / 2), 0), # x1, upper left
            max(int(image_height / 2) - (window_size / 2), 0), # y1, upper left
            min(int(image_width / 2) + (window_size / 2), image_width), # x2, lower right
            min(int(image_height / 2) + (window_size / 2), image_height)  # y2, lower right
        ])

        bbox_width = int(abs(bbox[0] - bbox[2]))
        bbox_height = int(abs(bbox[1] - bbox[3]))
        window_size = np.array([bbox_width, bbox_height])
        center = np.array([
            int(bbox[2] - int(bbox_width / 2)),
            int(bbox[3] - int(bbox_height / 2))
        ])

        assert bbox_width >= 32 and bbox_height >= 32

        center += np.array(conf_scale * np.array([conf_trans_x, conf_trans_y])).astype(int)

        processed_frames = []
        processed_poses = []
        normalized_frames = []
        visibility = []
        trans_matrices = []

        #TODO: transx, transy
        for frame, pose in zip(images, poses):
            trans_matrix, image = rotate_and_crop(frame, conf_angle, center, window_size)
            size_after_rotate = np.array([image.shape[1], image.shape[0]])

            image = resize(image, (256, 256), preserve_range=True)
            trans_matrix = scale(trans_matrix, 256 / size_after_rotate[0], 256 / size_after_rotate[1])

            #TODO: subsampling

            # randomly flip horizontal
            if conf_flip:
                image = np.fliplr(image)

                trans_matrix = translate(trans_matrix, -image.shape[1] / 2, -image.shape[0] / 2)
                trans_matrix = flip_h(trans_matrix)
                trans_matrix = translate(trans_matrix, image.shape[1] / 2, image.shape[0] / 2)

            transformed_pose = transform_pose(trans_matrix, pose)

            normalized_image = normalize_channels(image, power_factors=conf_exponents)
            normalized_frames.append(normalized_image)

            final_pose = np.empty((16, 3))
            final_pose[:] = np.nan

            for i in range(13):
                mpii_index = self.mpii_mapping[i][1]
                penn_index = self.mpii_mapping[i][0]

                joint_in_frame =  (0 <= transformed_pose[penn_index][0] <= 256) and (0 <= transformed_pose[penn_index][1] <= 256)
                if joint_in_frame:
                    final_pose[mpii_index, 0:2] = transformed_pose[penn_index]
                else:
                    final_pose[mpii_index, 0:2] = np.array([1e-9, 1e-9])

            final_pose[np.isnan(final_pose)] = 1e-9

            valid_joints = get_valid_joints(final_pose, need_sum=False)[:, 0:2]
            visibility = np.apply_along_axis(np.all, 1, valid_joints)
            final_pose[:, 2] = visibility

            processed_poses.append(final_pose)
            processed_frames.append(image)
            trans_matrices.append(trans_matrix.copy())

        return np.array(processed_frames), np.array(normalized_frames), np.array(processed_poses), np.array(trans_matrices)

mpii_joint_order = [
    "right ankle",
    "right knee",
    "right hip",
    "left hip",
    "left knee",
    "left ankle",
    "pelvis",
    "thorax",
    "upper neck",
    "head top",
    "right wrist",
    "right elbow",
    "right shoulder",
    "left shoulder",
    "left elbow",
    "left wrist"
]

class MPIIDataset(data.Dataset):

    '''
    What is (probably) happening with the train / val split of luvizon:
        - They load training data only and extract each person. Afterwards, they split it up
          into train / val and save it.
        - When I do it like below, almost exactly size(me) = size(train_luvizon) + size(val_luvizon)
    '''

    def __init__(self, root_dir, transform=None, use_random_parameters=True):

        self.root_dir = root_dir

        assert "annotations.mat" in os.listdir(self.root_dir)

        annotations = sio.loadmat(self.root_dir + "annotations")["RELEASE"]

        train_binary = annotations["img_train"][0][0][0]
        train_indeces = np.where(np.array(train_binary))[0]

        self.final_size=256

        if use_random_parameters:
            self.angles=np.array(range(-40, 40+1, 5))
            self.scales=np.array([0.7, 1., 1.3])
            self.channel_power_exponent = 0.01*np.array(range(90, 110+1, 2))
            self.flip_horizontal = np.array([0, 1])
        else:
            self.angles=np.array([0, 0, 0])
            self.scales=np.array([1., 1., 1.])
            self.flip_horizontal = np.array([0, 0])
            self.channel_power_exponent = None

        self.labels = []
        missing_annnotation_count = 0

        for idx in train_indeces:
            label = annotations["annolist"][0][0][0][idx]
            image_name = label["image"]["name"][0][0][0]

            annorect = label["annorect"]
            if len(annorect) == 0:
                # some labels are not present in the annotation file
                missing_annnotation_count += 1
                continue


            for rect_id in range(len(annorect[0])):
                ann = annorect[0][rect_id]
                head_coordinates = [
                    float(superflatten(ann["x1"])),
                    float(superflatten(ann["y1"])),
                    float(superflatten(ann["x2"])),
                    float(superflatten(ann["y2"]))
                ] # rect x1, y1, x2, y2
                try:
                    scale = superflatten(ann["scale"])

                    obj_pose = [
                        # rough position of human body (x,y)
                        superflatten(superflatten(ann["objpos"]["x"])),
                        superflatten(superflatten(ann["objpos"]["y"]))
                    ]

                    point = superflatten(ann["annopoints"]["point"])

                    xs = list(map(lambda x: superflatten(x), point["x"].flatten()))
                    ys = list(map(lambda x: superflatten(x), point["y"].flatten()))

                    # 0:r ankle 1:r knee 2:r hip 3:l hip 4:l knee 5:l ankle 6:pelvis 7:thorax 8:upper neck 9:head top 10:r wrist 11:r elbow 12:r shoulder 13:l shoulder 14:l elbow 15:l wrist
                    ids = list(map(lambda x: superflatten(x), point["id"].flatten()))
                    vs = []
                    for i,v in enumerate(point["is_visible"].flatten()):
                        try:
                            if ids[i] == 8 or ids[i] == 9:
                                # for some reason, upper neck and head annotations are always empty, probably  because they are always visible(?)
                                # set them to be always visible
                                vs.append(1)
                            else:
                                vs.append(superflatten(v))
                        except IndexError:
                            vs.append(0)
                except (IndexError, ValueError):
                    # all these fields are necessary, thus: skip if not present
                    missing_annnotation_count = missing_annnotation_count + 1
                    continue

                pose = {"x": xs, "y": ys, "visible": vs, "ids": ids}

                final_label = {
                    "head": np.array(head_coordinates),
                    "scale": scale,
                    "obj_pose": obj_pose,
                    "pose": pose,
                    "image_name": image_name
                }

                self.labels.append(final_label)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        label = self.labels[idx]
        full_image_path = self.root_dir + "images/" + label["image_name"]
        image = io.imread(full_image_path)
        original_image = image.copy()

        conf_scale = self.scales[np.random.randint(0, len(self.scales))]
        conf_angle = self.angles[np.random.randint(0, len(self.angles))]
        conf_flip = self.flip_horizontal[np.random.randint(0, len(self.flip_horizontal))]
        if self.channel_power_exponent is not None:
            conf_exponents = np.array([
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))],
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))],
                self.channel_power_exponent[np.random.randint(0, len(self.channel_power_exponent))]
            ])
        else:
            conf_exponents = None

        new_scale = label["scale"] * 1.25 # magic value
        new_objpose = np.array([label["obj_pose"][0], label["obj_pose"][1] + 12 * new_scale]) # magic values, no idea where they are comming from

        window_size = new_scale * conf_scale * 200

        image_width = image.shape[1]
        image_height = image.shape[0]

        bbox = np.array([
            max(new_objpose[0] - window_size / 2, 0), # x1, upper left
            max(new_objpose[1] - window_size / 2, 0), # y1, upper left
            min(new_objpose[0] + window_size / 2, image_width), # x2, lower right
            min(new_objpose[1] + window_size / 2, image_height)  # y2, lower right
        ])

        # rotate, then crop
        trans_matrix, image = rotate_and_crop(image, conf_angle, new_objpose, (window_size, window_size))
        size_after_rotate = np.array([image.shape[1], image.shape[0]])

        image = resize(image, (self.final_size, self.final_size), preserve_range=True)
        trans_matrix = scale(trans_matrix, self.final_size / size_after_rotate[0], self.final_size / size_after_rotate[1])

        old_pose = np.array([label["pose"]["x"], label["pose"]["y"]]).T
        old_objpos = np.array(label["obj_pose"])

        # randomly flip horizontal
        if conf_flip:
            image = np.fliplr(image)

            trans_matrix = translate(trans_matrix, -image.shape[1] / 2, -image.shape[0] / 2)
            trans_matrix = flip_h(trans_matrix)
            trans_matrix = translate(trans_matrix, image.shape[1] / 2, image.shape[0] / 2)

        trans_matrix = scale(trans_matrix, 1.0 / self.final_size, 1.0 / self.final_size)

        output = {}
        output["center"] = transform_2d_point(trans_matrix, old_objpos)
        output["original_size"] = torch.tensor([image_height, image_width], requires_grad=False)
        new_x = []
        new_y = []
        for idx, (x, y) in enumerate(old_pose):
            transformed_point = transform_2d_point(trans_matrix, np.array([x,y]))
            new_x.append(transformed_point[0])
            new_y.append(transformed_point[1])

        original_pose = np.empty((16, 3))
        original_pose[:] = np.nan

        for it, joint_index in enumerate(label["pose"]["ids"]):
            original_pose[joint_index, 0] = new_x[it]
            original_pose[joint_index, 1] = new_y[it]
            original_pose[joint_index, 2] = label["pose"]["visible"][it]

        original_pose[np.isnan(original_pose)] = -1e9

        normalized_pose = original_pose.copy()

        # According to paper:
        lower_one = np.apply_along_axis(np.all, 1, normalized_pose[:,0:2] < 1.0)
        bigger_zero = np.apply_along_axis(np.all, 1, normalized_pose[:,0:2] > 0.0)

        in_interval = np.logical_and(lower_one, bigger_zero)
        original_pose[:,2] = in_interval
        normalized_pose[:,2] = in_interval

        # calculating head size for pckh (according to paper)
        head_point_upper = np.array([label["head"][0], label["head"][1]])
        head_point_lower = np.array([label["head"][2], label["head"][3]])
        head_size = 0.6 * np.linalg.norm(head_point_upper - head_point_lower)

        image_normalized = normalize_channels(image, power_factors=conf_exponents)

        output["original_image"] = original_image
        output["bbox"] = bbox
        output["normalized_image"] = image_normalized
        output["normalized_pose"] = normalized_pose
        output["original_pose"] = original_pose
        output["head_size"] = np.array([head_size])
        output["trans_matrix"] = trans_matrix.copy()

        return output


class JHMDBDataset(data.Dataset):

    def __init__(self, root_dir, transform=None):
        self.root_dir = root_dir
        self.items = sorted(glob.glob(self.root_dir + "*/*"))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        item_path = self.items[idx]
        relative_path_split = item_path[len(self.root_dir):].split("/")
        action = relative_path_split[0]

        label = sio.loadmat(item_path + "/joint_positions")
        pose = label["pos_img"].T

        all_images = glob.glob(item_path + "/*.png")
        images = []
        for image_path in all_images:
            images.append(io.imread(image_path))

        image_height = len(images[0])
        image_width = len(images[0][0])

        visibility = []
        for frame_pose in pose:
            frame_visibility = []
            for joint in frame_pose:
                x = joint[0]
                y = joint[1]

                if x < 0 or x > image_width or y < 0 or y > image_height:
                    frame_visibility.append(0)
                else:
                    frame_visibility.append(1)
            visibility.append(frame_visibility)

        return {"action": action, "poses": pose, "images": images, "visibility": visibility}


#based on https://github.com/ufoym/imbalanced-dataset-sampler/blob/master/sampler.py
class ImbalancedDatasetSampler(data.sampler.Sampler):
    """Samples elements randomly from a given list of indices for imbalanced dataset
    Arguments:
        indices (list, optional): a list of indices
        num_samples (int, optional): number of samples to draw
    """

    def __init__(self, dataset, indices=None, num_samples=None):

        # if indices is not provided,
        # all elements in the dataset will be considered
        self.indices = list(range(len(dataset))) \
            if indices is None else indices

        # if num_samples is not provided,
        # draw `len(indices)` samples in each iteration
        self.num_samples = len(self.indices) \
            if num_samples is None else num_samples

        # distribution of classes in the dataset
        label_to_count = {}
        for idx in self.indices:
            label = self._get_label(dataset, idx)
            if label in label_to_count:
                label_to_count[label] += 1
            else:
                label_to_count[label] = 1

        # weight for each sample
        weights = [1.0 / label_to_count[self._get_label(dataset, idx)]
                   for idx in self.indices]
        self.weights = torch.DoubleTensor(weights)

    def _get_label(self, dataset, idx):
        return dataset[idx]["class"]

    def __iter__(self):
        return (self.indices[i] for i in torch.multinomial(
            self.weights, self.num_samples, replacement=True))

    def __len__(self):
        return self.num_samples


#train_loader = data.DataLoader(
#    dataset,
#    sampler=ImbalancedDatasetSampler(dataset, num_samples=10),
#    batch_size=5
#)

#for image in train_loader:
#    print(image)

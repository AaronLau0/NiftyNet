import os

import numpy as np
import numpy.ma as ma
import scipy.ndimage as ndimg
from scipy.ndimage.morphology import binary_fill_holes as fill_holes

import utilities.misc_io as io

try:
    from skimage import filters
except ImportError:
    from skimage import filter as filters

DEFAULT_CUTOFF = [0.01, 0.99]


def percentiles(img, mask, cutoff):
    perc = [cutoff[0],
            0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9,
            cutoff[1]]
    masked_img = ma.masked_array(img, np.logical_not(mask)).compressed()
    perc_results = np.percentile(masked_img, 100 * np.array(perc))
    # hist, bin = np.histogram(ma.compressed(masked_img), bins=50)
    return perc_results


def standardise_cutoff(cutoff, type_hist='quartile'):
    if cutoff is None:
        return DEFAULT_CUTOFF
    if len(cutoff) == 0:
        return DEFAULT_CUTOFF
    if len(cutoff) > 2:
        cutoff = np.unique([np.min(cutoff), np.max(cutoff)])
    if len(cutoff) == 1:
        return DEFAULT_CUTOFF
    if cutoff[0] > cutoff[1]:
        cutoff[0], cutoff[1] = cutoff[1], cutoff[0]
    cutoff[0] = max(0., cutoff[0])
    cutoff[1] = min(1., cutoff[1])
    # if type_hist == 'percentile':
    #     cutoff[0] = np.min([cutoff[0], 0.1])
    #     cutoff[1] = np.max([cutoff[1], 0.9])
    # if type_hist == 'quartile':
    #     cutoff[0] = np.min([cutoff[0], 0.25])
    #     cutoff[1] = np.max([cutoff[1], 0.75])
    return cutoff


def create_mapping_from_multimod_arrayfiles(array_files,
                                            list_modalities,
                                            cutoff,
                                            mask_type):
    perc_database = {}
    for p in array_files:
        img_data = io.csv_cell_to_volume_5d(p)
        numb_modalities = img_data.shape[3]
        numb_timepoints = img_data.shape[4]
        # to_do = {m: list_modalities[m] for m in list_modalities.keys() if
        #         list_modalities[m] < numb_modalities}
        for m in list_modalities.keys():
            if m not in perc_database.keys():
                perc_database[m] = []
            for t in range(0, numb_timepoints):
                img_temp = img_data[..., list_modalities[m], t]
                mask_temp = create_mask_img_3d(img_temp, mask_type)
                perc = percentiles(img_temp, mask_temp, cutoff)
                perc_database[m].append(perc)
    mapping = {}
    for m in list_modalities.keys():
        perc_database[m] = np.vstack(perc_database[m])
        s1, s2 = create_standard_range(perc_database[m])
        mapping[m] = create_mapping_perc(perc_database[m], s1, s2)
    return mapping


def create_standard_range(perc_database):
    # if pc1 > pc2:
    #     temp = pc2
    #     pc2 = pc1
    #     pc1 = temp
    # if pc1 < 0:
    #     pc1 =0
    # if pc2 > 16:
    #     pc2 = 16
    # if type == 'quartile':
    #     pc1 = np.min([pc1, 5])
    #     pc2 = np.max([pc2, 11])
    # if type == 'percentile':
    #     pc1 = np.min([pc1, 3])
    #     pc2 = np.max([pc2, 13])
    # left_side = perc_database[:, 6] - perc_database[:, 0]
    # right_side = perc_database[:, 12] - perc_database[:, 6]
    # range_min = (np.max(left_side) + np.max(right_side)) * np.max \
    #    ([np.max(left_side) / np.min(left_side),
    #      np.max(right_side) / np.min(right_side)])
    return 0., 100.


def read_mapping_file(mapping_file):
    mapping_dict = {}
    if not os.path.exists(mapping_file):
        return mapping_dict
    with open(mapping_file, "r") as f:
        for line in f:
            if len(line) <= 2:
                continue
            line = line.split()
            if len(line) < 2:
                continue
            map_name, map_value = line[0], map(float, line[1:])
            mapping_dict[map_name] = np.asarray(map_value)
    return mapping_dict


def force_writing_new_mapping(filename, mapping_dict):
    f = open(filename, 'w+')
    for mod in mapping_dict.keys():
        mapping_string = ' '.join(map(str, mapping_dict[mod]))
        string_fin = ('{} {}\n').format(mod, mapping_string)
        f.write(string_fin)


def create_mask_img_3d(img, type_mask='otsu_plus', thr=0.):
    assert img.ndim == 3
    mask_init = np.zeros_like(img, dtype=np.bool)
    if type_mask == 'threshold_plus':
        mask_init[img > thr] = 1
        mask_init[img <= thr] = 0
    elif type_mask == 'threshold_minus':
        mask_init[img < thr] = 1
        mask_init[img >= thr] = 0
    elif type_mask == 'otsu_plus':
        if not np.any(img):
            thr = 0
        else:
            thr = filters.threshold_otsu(img)
        mask_init[img > thr] = 1
        mask_init[img <= thr] = 0
    elif type_mask == 'otsu_minus':
        thr = filters.threshold_otsu(img)
        mask_init[img < thr] = 1
        mask_init[img >= thr] = 0
    mask_1 = ndimg.binary_dilation(mask_init, iterations=2)
    mask_bis = fill_holes(mask_1)
    # mask_fin = ndimg.binary_erosion(mask_bis, iterations=2)
    return mask_bis


def create_mapping_perc(perc_database, s1, s2):
    final_map = np.zeros([perc_database.shape[0], 13])
    for j in range(0, perc_database.shape[0]):
        lin_coeff = (s2 - s1) / (perc_database[j, 12] - perc_database[j, 0])
        affine_coeff = s1 - lin_coeff * perc_database[j, 0]
        for i in range(0, 13):
            final_map[j, i] = lin_coeff * perc_database[j, i] + affine_coeff
    return np.mean(final_map, axis=0)


def transform_for_mapping(img, mask, mapping, cutoff, type_hist='quartile'):
    range_to_use = None
    if type_hist == 'quartile':
        range_to_use = [0, 3, 6, 9, 12]
    if type_hist == 'percentile':
        range_to_use = [0, 1, 2, 4, 5, 6, 7, 8, 10, 11, 12]
    if type_hist == 'median':
        range_to_use = [0, 6, 12]
    cutoff = standardise_cutoff(cutoff, type_hist)
    perc = percentiles(img, mask, cutoff)
    # Apply linear histogram standardisation
    lin_img = np.ones_like(img, dtype=np.float32)
    aff_img = np.zeros_like(img, dtype=np.float32)
    affine_map = np.zeros([2, len(range_to_use) - 1])
    for i in range(len(range_to_use) - 1):
        affine_map[0, i] = (mapping[range_to_use[i + 1]] - mapping[range_to_use[i]]) / \
                           (perc[range_to_use[i + 1]] - perc[range_to_use[i]])
        affine_map[1, i] = mapping[range_to_use[i]] - affine_map[0, i] * perc[range_to_use[i]]
        lin_img[img >= perc[range_to_use[i]]] = affine_map[0, i]
        aff_img[img >= perc[range_to_use[i]]] = affine_map[1, i]
    # Note that values below cutoff[0] over cutoff[1] are also transformed at this stage
    lin_img[img < perc[range_to_use[0]]] = affine_map[0, 0]
    aff_img[img < perc[range_to_use[0]]] = affine_map[1, 0]
    new_img = np.multiply(lin_img, img) + aff_img
    # Apply smooth thresholding (exponential) below cutoff[0] and over cutoff[1]
    low_values = img <= perc[range_to_use[0]]
    new_img[low_values] = smooth_threshold(new_img[low_values], mode='low_value')
    high_values = img >= perc[range_to_use[-1]]
    new_img[high_values] = smooth_threshold(new_img[high_values], mode='high_value')
    # Apply mask and set background to zero
    new_img[mask == 0] = 0.
    return new_img


def smooth_threshold(value, mode='high_value'):
    smoothness = 1.
    if mode == 'high_value':
        affine = np.min(value)
        smooth_value = (value - affine) / smoothness
        smooth_value = (1. - np.exp((-1) * smooth_value)) + affine
    elif mode == 'low_value':
        affine = np.max(value)
        smooth_value = (value - affine) / smoothness
        smooth_value = (np.exp(smooth_value) - 1.) + affine
    else:
        smooth_value = value
    return smooth_value

## create mask for image if multimodal or not
# def create_mask_img_multimod(img, type_mask='otsu_plus', alpha=0.1,
#                             multimod=[0], multimod_type='and'):
#    if img.ndim == 3:
#        thr = alpha * img.mean()
#        return create_mask_img_3d(img, type_mask, thr)
#    if np.max(multimod) > img.shape[3]:
#        raise ValueError
#    if len(multimod) == 1:
#        thr = alpha * img.mean()
#
#        return create_mask_img_3d(img[..., np.min([multimod[0],
#                                                   img.shape[3]])], type_mask, thr)
#    else:
#        mask_init = np.zeros([img.shape[0], img.shape[1], img.shape[2],
#                              len(multimod)])
#        for i in range(0, len(multimod)):
#            thr = alpha * img[..., i].mean()
#            mask_temp = create_mask_img_3d(
#                img[..., np.min([multimod[i], img.shape[3]])],
#                type_mask, thr)
#            mask_init[:, :, :, i] = mask_temp
#
#        if multimod_type == 'or':
#            # Case when the mask if formed by the union of all modalities masks
#            mask_reduced = np.sum(mask_init, axis=3)
#            mask_reduced[mask_reduced > 0] = 1
#            return mask_reduced
#        elif multimod_type == 'and':
#            # Case when the mask is formed by the intersection of all
#            # modalities masks
#            mask_reduced = np.sum(mask_init, axis=3)
#            mask_reduced[mask_reduced < len(multimod) - 1] = 0
#            mask_reduced[mask_reduced > 0] = 1
#            return mask_reduced
#        else:
#            # Case when there will be one mask for each modality
#            return mask_init

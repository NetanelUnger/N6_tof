/**
 ******************************************************************************
 * @file    tof_image_processing.c
 * @brief   Allocation-free spatial filters for ToF depth images.
 ******************************************************************************
 */

#include "tof_image_processing.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>

typedef const float *(*TOF_ImageFilterApply_t)(
    float *image, float *workspace, uint32_t width, uint32_t height,
    const uint32_t *parameters);

typedef struct
{
    TOF_ImageFilterDescriptor_t descriptor;
    TOF_ImageFilterApply_t apply;
} TOF_ImageFilterRegistration_t;

static const float *tof_apply_none(float *image, float *workspace,
                                   uint32_t width, uint32_t height,
                                   const uint32_t *parameters);
static const float *tof_apply_box_blur(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       const uint32_t *parameters);
static const float *tof_apply_median(float *image, float *workspace,
                                     uint32_t width, uint32_t height,
                                     const uint32_t *parameters);
static const float *tof_apply_gaussian(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       const uint32_t *parameters);
static const float *tof_apply_sharpen(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters);
static const float *tof_apply_minimum(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters);
static const float *tof_apply_maximum(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters);
static const float *tof_apply_extremum(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       uint32_t radius, uint32_t find_maximum);
static uint32_t tof_gaussian_weight(uint32_t radius, uint32_t distance);
static uint32_t tof_depth_is_valid(float depth);

static const TOF_ImageFilterParameter_t tof_box_parameters[] =
{
    { "radius", "pixels", 1U, 3U, 1U },
    { "passes", "passes", 1U, 3U, 1U },
};

static const TOF_ImageFilterParameter_t tof_median_parameters[] =
{
    { "radius", "pixels", 1U, 2U, 1U },
    { "threshold_mm", "mm", 0U, 1000U, 100U },
};

static const TOF_ImageFilterParameter_t tof_gaussian_parameters[] =
{
    { "radius", "pixels", 1U, 2U, 1U },
    { "passes", "passes", 1U, 3U, 1U },
};

static const TOF_ImageFilterParameter_t tof_sharpen_parameters[] =
{
    { "radius", "pixels", 1U, 3U, 1U },
    { "amount_percent", "%", 0U, 200U, 100U },
};

static const TOF_ImageFilterParameter_t tof_extremum_parameters[] =
{
    { "radius", "pixels", 1U, 3U, 1U },
};

/* Adding a filter requires one registration and one allocation-free callback. */
static const TOF_ImageFilterRegistration_t tof_filters[] =
{
    {
        { TOF_IMAGE_FILTER_NONE, "OFF", "Off", "unprocessed depth",
          NULL, 0U },
        tof_apply_none
    },
    {
        { TOF_IMAGE_FILTER_BOX_BLUR, "BOX", "Box blur",
          "averages valid neighboring depth values",
          tof_box_parameters,
          sizeof(tof_box_parameters) / sizeof(tof_box_parameters[0]) },
        tof_apply_box_blur
    },
    {
        { TOF_IMAGE_FILTER_MEDIAN, "MEDIAN", "Median",
          "removes isolated depth outliers while preserving edges",
          tof_median_parameters,
          sizeof(tof_median_parameters) / sizeof(tof_median_parameters[0]) },
        tof_apply_median
    },
    {
        { TOF_IMAGE_FILTER_GAUSSIAN, "GAUSSIAN", "Gaussian",
          "weighted blur with less blockiness than box averaging",
          tof_gaussian_parameters,
          sizeof(tof_gaussian_parameters) /
          sizeof(tof_gaussian_parameters[0]) },
        tof_apply_gaussian
    },
    {
        { TOF_IMAGE_FILTER_SHARPEN, "SHARPEN", "Sharpen",
          "unsharp masking that emphasizes depth transitions",
          tof_sharpen_parameters,
          sizeof(tof_sharpen_parameters) /
          sizeof(tof_sharpen_parameters[0]) },
        tof_apply_sharpen
    },
    {
        { TOF_IMAGE_FILTER_MINIMUM, "MIN", "Minimum",
          "selects the nearest valid depth in each neighborhood",
          tof_extremum_parameters,
          sizeof(tof_extremum_parameters) /
          sizeof(tof_extremum_parameters[0]) },
        tof_apply_minimum
    },
    {
        { TOF_IMAGE_FILTER_MAXIMUM, "MAX", "Maximum",
          "selects the farthest valid depth in each neighborhood",
          tof_extremum_parameters,
          sizeof(tof_extremum_parameters) /
          sizeof(tof_extremum_parameters[0]) },
        tof_apply_maximum
    },
};

_Static_assert((sizeof(tof_filters) / sizeof(tof_filters[0])) ==
               TOF_IMAGE_FILTER_COUNT,
               "Every ToF filter enum value must have a registration");

void TOF_ImageProcessing_InitConfig(TOF_ImageProcessingConfig_t *config)
{
    size_t filter_index;

    if (config == NULL)
    {
        return;
    }

    config->selected_filter = TOF_IMAGE_FILTER_NONE;
    for (filter_index = 0U; filter_index < TOF_IMAGE_FILTER_COUNT;
         ++filter_index)
    {
        size_t parameter_index;
        const TOF_ImageFilterDescriptor_t *descriptor =
            &tof_filters[filter_index].descriptor;

        for (parameter_index = 0U;
             parameter_index < TOF_IMAGE_FILTER_MAX_PARAMETERS;
             ++parameter_index)
        {
            config->values[filter_index][parameter_index] =
                (parameter_index < descriptor->parameter_count) ?
                descriptor->parameters[parameter_index].default_value : 0U;
        }
    }
}

const TOF_ImageFilterDescriptor_t *TOF_ImageProcessing_GetDescriptor(
    TOF_ImageFilter_t filter)
{
    if ((uint32_t)filter >= (uint32_t)TOF_IMAGE_FILTER_COUNT)
    {
        return NULL;
    }
    return &tof_filters[(size_t)filter].descriptor;
}

const TOF_ImageFilterDescriptor_t *TOF_ImageProcessing_GetDescriptorByIndex(
    size_t index)
{
    if (index >= (sizeof(tof_filters) / sizeof(tof_filters[0])))
    {
        return NULL;
    }
    return &tof_filters[index].descriptor;
}

size_t TOF_ImageProcessing_GetFilterCount(void)
{
    return sizeof(tof_filters) / sizeof(tof_filters[0]);
}

TOF_ImageProcessingStatus_t TOF_ImageProcessing_SelectFilter(
    TOF_ImageProcessingConfig_t *config, TOF_ImageFilter_t filter)
{
    if (config == NULL)
    {
        return TOF_IMAGE_PROCESSING_INVALID_ARGUMENT;
    }
    if ((uint32_t)filter >= (uint32_t)TOF_IMAGE_FILTER_COUNT)
    {
        return TOF_IMAGE_PROCESSING_INVALID_FILTER;
    }

    config->selected_filter = filter;
    return TOF_IMAGE_PROCESSING_OK;
}

TOF_ImageProcessingStatus_t TOF_ImageProcessing_SetParameter(
    TOF_ImageProcessingConfig_t *config, TOF_ImageFilter_t filter,
    size_t parameter_index, uint32_t value)
{
    const TOF_ImageFilterDescriptor_t *descriptor;
    const TOF_ImageFilterParameter_t *parameter;

    if (config == NULL)
    {
        return TOF_IMAGE_PROCESSING_INVALID_ARGUMENT;
    }
    descriptor = TOF_ImageProcessing_GetDescriptor(filter);
    if (descriptor == NULL)
    {
        return TOF_IMAGE_PROCESSING_INVALID_FILTER;
    }
    if (parameter_index >= descriptor->parameter_count)
    {
        return TOF_IMAGE_PROCESSING_INVALID_PARAMETER;
    }

    parameter = &descriptor->parameters[parameter_index];
    if ((value < parameter->minimum) || (value > parameter->maximum))
    {
        return TOF_IMAGE_PROCESSING_VALUE_OUT_OF_RANGE;
    }

    config->values[(size_t)filter][parameter_index] = value;
    return TOF_IMAGE_PROCESSING_OK;
}

const float *TOF_ImageProcessing_Apply(
    float *image, float *workspace, uint32_t width, uint32_t height,
    const TOF_ImageProcessingConfig_t *config)
{
    TOF_ImageFilter_t filter;

    if ((image == NULL) || (workspace == NULL) || (config == NULL) ||
        (width == 0U) || (height == 0U) || (image == workspace))
    {
        return image;
    }

    filter = config->selected_filter;
    if ((uint32_t)filter >= (uint32_t)TOF_IMAGE_FILTER_COUNT)
    {
        return image;
    }

    return tof_filters[(size_t)filter].apply(
        image, workspace, width, height, config->values[(size_t)filter]);
}

static const float *tof_apply_none(float *image, float *workspace,
                                   uint32_t width, uint32_t height,
                                   const uint32_t *parameters)
{
    (void)workspace;
    (void)width;
    (void)height;
    (void)parameters;
    return image;
}

static const float *tof_apply_box_blur(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       const uint32_t *parameters)
{
    const float *source = image;
    uint32_t radius = parameters[0];
    uint32_t passes = parameters[1];
    uint32_t pass;

    for (pass = 0U; pass < passes; ++pass)
    {
        float *destination = (source == image) ? workspace : image;
        uint32_t y;

        for (y = 0U; y < height; ++y)
        {
            uint32_t x;
            for (x = 0U; x < width; ++x)
            {
                float sum = 0.0f;
                uint32_t valid_count = 0U;
                int32_t dy;

                for (dy = -(int32_t)radius; dy <= (int32_t)radius; ++dy)
                {
                    int32_t sample_y = (int32_t)y + dy;
                    int32_t dx;
                    if ((sample_y < 0) || (sample_y >= (int32_t)height))
                    {
                        continue;
                    }

                    for (dx = -(int32_t)radius; dx <= (int32_t)radius; ++dx)
                    {
                        int32_t sample_x = (int32_t)x + dx;
                        float sample;
                        if ((sample_x < 0) || (sample_x >= (int32_t)width))
                        {
                            continue;
                        }
                        sample = source[((size_t)sample_y * width) +
                                        (size_t)sample_x];
                        if (tof_depth_is_valid(sample) != 0U)
                        {
                            sum += sample;
                            ++valid_count;
                        }
                    }
                }

                destination[((size_t)y * width) + x] =
                    (valid_count != 0U) ? (sum / (float)valid_count) :
                    source[((size_t)y * width) + x];
            }
        }
        source = destination;
    }

    return source;
}

static const float *tof_apply_median(float *image, float *workspace,
                                     uint32_t width, uint32_t height,
                                     const uint32_t *parameters)
{
    uint32_t radius = parameters[0];
    float threshold = (float)parameters[1];
    uint32_t y;

    for (y = 0U; y < height; ++y)
    {
        uint32_t x;
        for (x = 0U; x < width; ++x)
        {
            float samples[25];
            size_t sample_count = 0U;
            int32_t dy;

            for (dy = -(int32_t)radius; dy <= (int32_t)radius; ++dy)
            {
                int32_t sample_y = (int32_t)y + dy;
                int32_t dx;
                if ((sample_y < 0) || (sample_y >= (int32_t)height))
                {
                    continue;
                }

                for (dx = -(int32_t)radius; dx <= (int32_t)radius; ++dx)
                {
                    int32_t sample_x = (int32_t)x + dx;
                    float sample;
                    if ((sample_x < 0) || (sample_x >= (int32_t)width))
                    {
                        continue;
                    }
                    sample = image[((size_t)sample_y * width) +
                                   (size_t)sample_x];
                    if (tof_depth_is_valid(sample) != 0U)
                    {
                        size_t insertion = sample_count;
                        while ((insertion != 0U) &&
                               (samples[insertion - 1U] > sample))
                        {
                            samples[insertion] = samples[insertion - 1U];
                            --insertion;
                        }
                        samples[insertion] = sample;
                        ++sample_count;
                    }
                }
            }

            if (sample_count == 0U)
            {
                workspace[((size_t)y * width) + x] =
                    image[((size_t)y * width) + x];
            }
            else
            {
                float center = image[((size_t)y * width) + x];
                float median = samples[sample_count / 2U];
                if ((threshold == 0.0f) ||
                    (tof_depth_is_valid(center) == 0U) ||
                    (fabsf(center - median) > threshold))
                {
                    workspace[((size_t)y * width) + x] = median;
                }
                else
                {
                    workspace[((size_t)y * width) + x] = center;
                }
            }
        }
    }

    return workspace;
}

static const float *tof_apply_gaussian(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       const uint32_t *parameters)
{
    uint32_t radius = parameters[0];
    uint32_t passes = parameters[1];
    uint32_t pass;

    for (pass = 0U; pass < passes; ++pass)
    {
        uint32_t y;

        for (y = 0U; y < height; ++y)
        {
            uint32_t x;
            for (x = 0U; x < width; ++x)
            {
                float sum = 0.0f;
                uint32_t weight_sum = 0U;
                int32_t dx;

                for (dx = -(int32_t)radius; dx <= (int32_t)radius; ++dx)
                {
                    int32_t sample_x = (int32_t)x + dx;
                    if ((sample_x >= 0) && (sample_x < (int32_t)width))
                    {
                        float sample = image[((size_t)y * width) +
                                             (size_t)sample_x];
                        if (tof_depth_is_valid(sample) != 0U)
                        {
                            uint32_t distance = (dx < 0) ?
                                (uint32_t)(-dx) : (uint32_t)dx;
                            uint32_t weight =
                                tof_gaussian_weight(radius, distance);
                            sum += sample * (float)weight;
                            weight_sum += weight;
                        }
                    }
                }
                workspace[((size_t)y * width) + x] =
                    (weight_sum != 0U) ? (sum / (float)weight_sum) :
                    image[((size_t)y * width) + x];
            }
        }

        for (y = 0U; y < height; ++y)
        {
            uint32_t x;
            for (x = 0U; x < width; ++x)
            {
                float sum = 0.0f;
                uint32_t weight_sum = 0U;
                int32_t dy;

                for (dy = -(int32_t)radius; dy <= (int32_t)radius; ++dy)
                {
                    int32_t sample_y = (int32_t)y + dy;
                    if ((sample_y >= 0) && (sample_y < (int32_t)height))
                    {
                        float sample = workspace[((size_t)sample_y * width) + x];
                        if (tof_depth_is_valid(sample) != 0U)
                        {
                            uint32_t distance = (dy < 0) ?
                                (uint32_t)(-dy) : (uint32_t)dy;
                            uint32_t weight =
                                tof_gaussian_weight(radius, distance);
                            sum += sample * (float)weight;
                            weight_sum += weight;
                        }
                    }
                }
                image[((size_t)y * width) + x] =
                    (weight_sum != 0U) ? (sum / (float)weight_sum) :
                    workspace[((size_t)y * width) + x];
            }
        }
    }

    return image;
}

static const float *tof_apply_sharpen(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters)
{
    uint32_t blur_parameters[2] = { parameters[0], 1U };
    float amount = (float)parameters[1] / 100.0f;
    size_t pixel_count = (size_t)width * height;
    size_t index;

    (void)tof_apply_box_blur(image, workspace, width, height,
                             blur_parameters);
    for (index = 0U; index < pixel_count; ++index)
    {
        float center = image[index];
        float blurred = workspace[index];

        if ((tof_depth_is_valid(center) != 0U) &&
            (tof_depth_is_valid(blurred) != 0U))
        {
            float sharpened = center + (amount * (center - blurred));
            image[index] = (sharpened > 0.0f) ? sharpened : 1.0f;
        }
    }
    return image;
}

static const float *tof_apply_minimum(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters)
{
    return tof_apply_extremum(image, workspace, width, height,
                              parameters[0], 0U);
}

static const float *tof_apply_maximum(float *image, float *workspace,
                                      uint32_t width, uint32_t height,
                                      const uint32_t *parameters)
{
    return tof_apply_extremum(image, workspace, width, height,
                              parameters[0], 1U);
}

static const float *tof_apply_extremum(float *image, float *workspace,
                                       uint32_t width, uint32_t height,
                                       uint32_t radius, uint32_t find_maximum)
{
    uint32_t y;

    for (y = 0U; y < height; ++y)
    {
        uint32_t x;
        for (x = 0U; x < width; ++x)
        {
            float selected = 0.0f;
            uint32_t found = 0U;
            int32_t dy;

            for (dy = -(int32_t)radius; dy <= (int32_t)radius; ++dy)
            {
                int32_t sample_y = (int32_t)y + dy;
                int32_t dx;
                if ((sample_y < 0) || (sample_y >= (int32_t)height))
                {
                    continue;
                }

                for (dx = -(int32_t)radius; dx <= (int32_t)radius; ++dx)
                {
                    int32_t sample_x = (int32_t)x + dx;
                    float sample;
                    if ((sample_x < 0) || (sample_x >= (int32_t)width))
                    {
                        continue;
                    }
                    sample = image[((size_t)sample_y * width) +
                                   (size_t)sample_x];
                    if ((tof_depth_is_valid(sample) != 0U) &&
                        ((found == 0U) ||
                         ((find_maximum != 0U) && (sample > selected)) ||
                         ((find_maximum == 0U) && (sample < selected))))
                    {
                        selected = sample;
                        found = 1U;
                    }
                }
            }

            workspace[((size_t)y * width) + x] =
                (found != 0U) ? selected : image[((size_t)y * width) + x];
        }
    }
    return workspace;
}

static uint32_t tof_gaussian_weight(uint32_t radius, uint32_t distance)
{
    static const uint8_t radius_one[] = { 2U, 1U };
    static const uint8_t radius_two[] = { 6U, 4U, 1U };

    return (radius == 1U) ? radius_one[distance] : radius_two[distance];
}

static uint32_t tof_depth_is_valid(float depth)
{
    return (isfinite(depth) && (depth > 0.0f)) ? 1U : 0U;
}

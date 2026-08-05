/**
 ******************************************************************************
 * @file    tof_image_processing.h
 * @brief   Allocation-free spatial filters for ToF depth images.
 ******************************************************************************
 */

#ifndef TOF_IMAGE_PROCESSING_H
#define TOF_IMAGE_PROCESSING_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TOF_IMAGE_FILTER_MAX_PARAMETERS (2U)

typedef enum
{
    TOF_IMAGE_FILTER_NONE = 0,
    TOF_IMAGE_FILTER_BOX_BLUR,
    TOF_IMAGE_FILTER_MEDIAN,
    TOF_IMAGE_FILTER_GAUSSIAN,
    TOF_IMAGE_FILTER_SHARPEN,
    TOF_IMAGE_FILTER_MINIMUM,
    TOF_IMAGE_FILTER_MAXIMUM,
    TOF_IMAGE_FILTER_COUNT
} TOF_ImageFilter_t;

typedef struct
{
    const char *name;
    const char *unit;
    uint32_t minimum;
    uint32_t maximum;
    uint32_t default_value;
} TOF_ImageFilterParameter_t;

typedef struct
{
    TOF_ImageFilter_t filter;
    const char *command;
    const char *display_name;
    const char *description;
    const TOF_ImageFilterParameter_t *parameters;
    size_t parameter_count;
} TOF_ImageFilterDescriptor_t;

typedef struct
{
    TOF_ImageFilter_t selected_filter;
    uint32_t values[TOF_IMAGE_FILTER_COUNT][TOF_IMAGE_FILTER_MAX_PARAMETERS];
} TOF_ImageProcessingConfig_t;

typedef enum
{
    TOF_IMAGE_PROCESSING_OK = 0,
    TOF_IMAGE_PROCESSING_INVALID_ARGUMENT = -1,
    TOF_IMAGE_PROCESSING_INVALID_FILTER = -2,
    TOF_IMAGE_PROCESSING_INVALID_PARAMETER = -3,
    TOF_IMAGE_PROCESSING_VALUE_OUT_OF_RANGE = -4
} TOF_ImageProcessingStatus_t;

void TOF_ImageProcessing_InitConfig(TOF_ImageProcessingConfig_t *config);

const TOF_ImageFilterDescriptor_t *TOF_ImageProcessing_GetDescriptor(
    TOF_ImageFilter_t filter);

const TOF_ImageFilterDescriptor_t *TOF_ImageProcessing_GetDescriptorByIndex(
    size_t index);

size_t TOF_ImageProcessing_GetFilterCount(void);

TOF_ImageProcessingStatus_t TOF_ImageProcessing_SelectFilter(
    TOF_ImageProcessingConfig_t *config, TOF_ImageFilter_t filter);

TOF_ImageProcessingStatus_t TOF_ImageProcessing_SetParameter(
    TOF_ImageProcessingConfig_t *config, TOF_ImageFilter_t filter,
    size_t parameter_index, uint32_t value);

/*
 * Apply the selected filter without allocation. The returned pointer is either
 * image or workspace and remains valid until either buffer is reused.
 */
const float *TOF_ImageProcessing_Apply(
    float *image, float *workspace, uint32_t width, uint32_t height,
    const TOF_ImageProcessingConfig_t *config);

#ifdef __cplusplus
}
#endif

#endif /* TOF_IMAGE_PROCESSING_H */

#pragma once
#include "FreeRTOS.h"
typedef void *SemaphoreHandle_t;
SemaphoreHandle_t xSemaphoreCreateMutex(void);
int xSemaphoreTake(SemaphoreHandle_t handle, TickType_t ticks);
int xSemaphoreGive(SemaphoreHandle_t handle);
void vSemaphoreDelete(SemaphoreHandle_t handle);

<template>
  <div class="schedule-section">
    <div class="schedule-controls">
      <div class="schedule-topline">
        <div
          class="publish-mode-selector"
          :class="scheduleEnabled ? 'is-scheduled' : 'is-immediate'"
          role="radiogroup"
          aria-label="发布方式"
        >
          <button
            type="button"
            class="mode-option mode-option--immediate"
            :class="{ active: !scheduleEnabled }"
            role="radio"
            :aria-checked="!scheduleEnabled"
            @click="setScheduleMode(false)"
          >
            <el-icon><VideoPlay /></el-icon>
            <span>立即发布</span>
          </button>
          <button
            type="button"
            class="mode-option mode-option--scheduled"
            :class="{ active: scheduleEnabled }"
            role="radio"
            :aria-checked="scheduleEnabled"
            @click="setScheduleMode(true)"
          >
            <el-icon><Timer /></el-icon>
            <span>定时发布</span>
          </button>
        </div>
        <div class="mode-summary" :class="scheduleEnabled ? 'is-scheduled' : 'is-immediate'">
          <el-icon><Check /></el-icon>
          <span>{{ scheduleEnabled ? scheduleSummary : '提交后马上进入发布流程' }}</span>
        </div>
      </div>
      <div v-if="scheduleEnabled" class="schedule-settings">
        <div class="schedule-item schedule-item--count">
          <span class="label">每天</span>
          <el-input-number v-model="videosPerDay" :min="1" :max="55" :controls="false" />
          <span class="unit">条</span>
        </div>
        <div class="schedule-item schedule-item--start">
          <span class="label">从</span>
          <el-select v-model="startDays" placeholder="选择开始天数">
            <el-option label="明天" :value="0" />
            <el-option label="后天" :value="1" />
          </el-select>
          <span class="unit">开始</span>
        </div>
        <div class="schedule-item schedule-item--jitter">
          <span class="label">随机</span>
          <el-input-number v-model="timeJitterMinutes" :min="0" :max="120" :step="5" :controls="false" />
          <span class="unit">分钟</span>
        </div>
        <div class="schedule-item schedule-item--times">
          <span class="label">基准时间</span>
          <div class="time-selectors">
            <el-time-select
              v-for="(time, index) in dailyTimes"
              :key="index"
              v-model="dailyTimes[index]"
              start="00:00"
              step="00:30"
              end="23:30"
              placeholder="时间"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { Check, Timer, VideoPlay } from '@element-plus/icons-vue'

const props = defineProps({
  scheduleEnabled: {
    type: Boolean,
    default: false
  },
  videosPerDay: {
    type: Number,
    default: 1
  },
  dailyTimes: {
    type: Array,
    default: () => ['10:00']
  },
  startDays: {
    type: Number,
    default: 0
  },
  timeJitterMinutes: {
    type: Number,
    default: 15
  }
})

const emit = defineEmits(['update:scheduleEnabled', 'update:videosPerDay', 'update:dailyTimes', 'update:startDays', 'update:timeJitterMinutes'])

const scheduleEnabled = computed({
  get: () => props.scheduleEnabled,
  set: (value) => emit('update:scheduleEnabled', value)
})

const videosPerDay = computed({
  get: () => props.videosPerDay,
  set: (value) => {
    const count = Number(value) || 1
    emit('update:videosPerDay', count)
    syncTimeSlots(count)
  }
})

const dailyTimes = computed({
  get: () => props.dailyTimes,
  set: (value) => emit('update:dailyTimes', value)
})

const startDays = computed({
  get: () => props.startDays,
  set: (value) => emit('update:startDays', value)
})

const timeJitterMinutes = computed({
  get: () => props.timeJitterMinutes,
  set: (value) => emit('update:timeJitterMinutes', Number(value) || 0)
})

const scheduleSummary = computed(() => {
  const jitter = timeJitterMinutes.value ? `，前后随机 ${timeJitterMinutes.value} 分钟` : ''
  return `每天 ${videosPerDay.value} 条，${startDays.value === 0 ? '明天' : '后天'}开始${jitter}`
})

const setScheduleMode = (value) => {
  scheduleEnabled.value = value
  handleScheduleChange(value)
}

const handleScheduleChange = (value) => {
  if (!value) {
    // 关闭定时发布时，重置为默认值
    emit('update:videosPerDay', 1)
    emit('update:dailyTimes', ['10:00'])
    emit('update:startDays', 0)
    emit('update:timeJitterMinutes', 15)
  }
}

const syncTimeSlots = (count) => {
  const current = [...dailyTimes.value]
  if (current.length > count) {
    emit('update:dailyTimes', current.slice(0, count))
    return
  }
  while (current.length < count) {
    current.push(current[current.length - 1] || '10:00')
  }
  emit('update:dailyTimes', current)
}

watch(() => props.videosPerDay, (count) => syncTimeSlots(Number(count) || 1))
</script>

<style lang="scss" scoped>
.schedule-section {
  margin-bottom: 0;
  
  h3 {
    font-size: 16px;
    font-weight: 500;
    color: #303133;
    margin: 0 0 10px 0;
  }
  
  .schedule-controls {
    display: flex;
    flex-direction: column;
    gap: 10px;

    .schedule-topline {
      display: grid;
      grid-template-columns: minmax(280px, 380px) minmax(260px, 1fr);
      gap: 10px;
      align-items: center;
    }

    .publish-mode-selector {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      padding: 6px;
      background: rgba(248, 250, 252, 0.92);
      border: 1px solid rgba(15, 23, 42, 0.08);
      border-radius: 18px;
      transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;

      &.is-immediate {
        background: linear-gradient(180deg, rgba(240, 253, 244, 0.82), rgba(248, 250, 252, 0.95));
        border-color: rgba(34, 197, 94, 0.24);
      }

      &.is-scheduled {
        background: linear-gradient(180deg, rgba(239, 246, 255, 0.9), rgba(248, 250, 252, 0.95));
        border-color: rgba(64, 158, 255, 0.28);
      }
    }

    .mode-option {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      min-height: 42px;
      padding: 0 14px;
      color: #687386;
      font-size: 13px;
      font-weight: 760;
      text-align: center;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.68);
      border: 1px solid rgba(15, 23, 42, 0.08);
      border-radius: 15px;
      outline: none;
      transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, color 0.18s ease, transform 0.18s ease;

      &:hover {
        color: #1f2937;
        background: rgba(255, 255, 255, 0.94);
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
      }

      &:focus-visible {
        box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.18);
      }

      &.active {
        color: #0f172a;
        background: #ffffff;
      }

      &.mode-option--immediate.active {
        border-color: rgba(34, 197, 94, 0.62);
        box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.14), 0 16px 34px rgba(15, 23, 42, 0.08);
      }

      &.mode-option--scheduled.active {
        border-color: rgba(64, 158, 255, 0.68);
        box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.14), 0 16px 34px rgba(15, 23, 42, 0.08);
      }

      &.mode-option--immediate.active .mode-icon {
        color: #16a34a;
        background: rgba(220, 252, 231, 0.95);
        box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.22);
      }

      &.mode-option--scheduled.active .mode-icon {
        color: #1677d2;
        background: rgba(219, 234, 254, 0.95);
        box-shadow: inset 0 0 0 1px rgba(64, 158, 255, 0.22);
      }

      &:active {
        transform: scale(0.99);
      }
    }

    .mode-option .el-icon {
      font-size: 17px;
    }

    .mode-summary {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 42px;
      padding: 0 14px;
      color: #4b5563;
      font-size: 13px;
      font-weight: 650;
      border: 1px solid transparent;
      border-radius: 12px;

      &.is-immediate {
        color: #15803d;
        background: rgba(240, 253, 244, 0.88);
        border-color: rgba(34, 197, 94, 0.18);
      }

      &.is-scheduled {
        color: #1677d2;
        background: rgba(239, 246, 255, 0.9);
        border-color: rgba(64, 158, 255, 0.2);
      }
    }

    .schedule-settings {
      display: grid;
      grid-template-columns: minmax(120px, 0.6fr) minmax(150px, 0.7fr) minmax(150px, 0.7fr) minmax(280px, 2fr);
      gap: 10px;
      align-items: stretch;
      padding: 10px;
      background: rgba(248, 250, 252, 0.82);
      border: 1px solid rgba(15, 23, 42, 0.06);
      border-radius: 16px;

      .schedule-item {
        display: flex;
        align-items: center;
        gap: 7px;
        min-width: 0;
        min-height: 42px;
        padding: 7px 9px;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(15, 23, 42, 0.06);
        border-radius: 12px;

        .label {
          flex: 0 0 auto;
          min-width: auto;
          line-height: 1;
          color: #4b5563;
          font-size: 13px;
          font-weight: 650;
        }

        .unit {
          flex: 0 0 auto;
          color: #6b7280;
          font-size: 12px;
          font-weight: 650;
        }

        :deep(.el-input-number) {
          width: 58px;
        }

        :deep(.el-input__wrapper),
        :deep(.el-select__wrapper) {
          min-height: 30px;
          border-radius: 9px;
        }

        :deep(.el-input__inner) {
          text-align: center;
        }

        &.schedule-item--start {
          :deep(.el-select) {
            width: 76px;
          }
        }

        &.schedule-item--jitter {
          :deep(.el-input-number) {
            width: 64px;
          }
        }

        &.schedule-item--times {
          align-items: flex-start;
          grid-column: auto;

          .label {
            padding-top: 10px;
          }
        }

        .time-selectors {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          align-items: center;
          min-width: 0;
          
          .el-time-select {
            width: 94px;
          }
        }
      }
    }
  }
}

@media (max-width: 720px) {
  .schedule-section {
    .schedule-controls {
      .schedule-topline,
      .publish-mode-selector {
        grid-template-columns: 1fr;
      }

      .schedule-settings {
        grid-template-columns: 1fr;
      }

      .schedule-settings .schedule-item {
        flex-wrap: wrap;

        .label {
          min-width: 0;
          line-height: 1.3;
        }
      }
    }
  }
}
</style>

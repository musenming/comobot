<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useThemeStore } from '../stores/theme'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  data: number[]
  labels?: string[]
  color?: string
  height?: string
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
const themeStore = useThemeStore()

function renderChart() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  const lineColor = props.color || (themeStore.isDark ? '#FAFAFA' : '#0A0A0A')
  chart.setOption({
    grid: { top: 8, right: 8, bottom: 8, left: 8 },
    xAxis: {
      type: 'category',
      show: false,
      data: props.labels || props.data.map((_, i) => `${i}`),
    },
    yAxis: { type: 'value', show: false },
    tooltip: {
      trigger: 'axis',
      backgroundColor: themeStore.isDark ? '#1C1C22' : '#FFFFFF',
      borderColor: themeStore.isDark ? 'rgba(255,255,255,0.08)' : '#E8E8E8',
      textStyle: {
        color: themeStore.isDark ? '#FAFAFA' : '#0A0A0A',
        fontSize: 12,
      },
    },
    series: [{
      type: 'line',
      data: props.data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: lineColor },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: lineColor + '20' },
          { offset: 1, color: lineColor + '00' },
        ]),
      },
    }],
  })
}

onMounted(() => {
  renderChart()
  window.addEventListener('resize', () => chart?.resize())
})

watch(() => [props.data, themeStore.isDark], renderChart, { deep: true })

onUnmounted(() => {
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartRef" :style="{ width: '100%', height: height || '120px' }" />
</template>

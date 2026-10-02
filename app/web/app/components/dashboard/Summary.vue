<script setup lang="ts">
defineProps<{
  items: { label: string, value: string | number, icon: string, note?: string }[]
  variant?: 'workforce' | 'executive' | 'technical' | 'compact' | 'paired'
  label?: string
  pending?: boolean
  unavailable?: boolean
}>()
const numberFormat = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 20 })
const displayValue = (value: number | string) => typeof value === 'number' ? numberFormat.format(value) : value
</script>

<template>
  <dl
    class="dashboard-summary"
    :class="{ 'dashboard-summary--compact': variant === 'compact', 'dashboard-summary--workforce': !variant || variant === 'workforce', 'dashboard-summary--technical': variant === 'technical', 'dashboard-summary--executive': variant === 'executive', 'dashboard-summary--paired': variant === 'paired' }"
    :aria-label="label || 'Dashboard summary'"
    :aria-busy="pending"
  >
    <div
      v-for="item in items"
      :key="item.label"
      class="dashboard-summary-item"
    >
      <dt>
        <UIcon
          :name="item.icon"
          class="size-4 shrink-0"
        />
        <span>{{ item.label }}</span>
      </dt>
      <dd>
        <USkeleton
          v-if="pending && unavailable"
          class="h-8 w-16"
        />
        <template v-else>
          {{ unavailable ? '—' : displayValue(item.value) }}
        </template>
        <small v-if="item.note && !unavailable" class="dashboard-description">{{ item.note }}</small>
      </dd>
    </div>
  </dl>
</template>

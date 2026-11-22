<template>
  <div>
    <!-- vue/no-restricted-class -->
    <span class="text-grey">muted</span>
    <span class="text-grey-darken-1">muted shade</span>

    <!-- vue/no-restricted-static-attribute -->
    <v-chip color="purple">banned material color</v-chip>

    <!-- vue/no-restricted-syntax: v-snackbar, v-btn-toggle, hex attr, numeric rgba attr -->
    <v-snackbar :model-value="true">local snackbar</v-snackbar>
    <v-btn-toggle :model-value="0"><v-btn>A</v-btn></v-btn-toggle>
    <svg>
      <circle fill="#a78bfa" stroke="rgba(10, 132, 255, 0.5)" r="5" />
    </svg>
    <div :style="{ color: '#34d399', background: 'rgba(0, 0, 0, 0.5)' }" />
  </div>
</template>

<script setup>
const now = new Date();

// no-alert
alert("native alert");
confirm("native confirm");

// no-restricted-properties (timezone discipline)
export const formatted = [
  now.toLocaleString(),
  now.toLocaleDateString(),
  now.toLocaleTimeString(),
  now.getHours(),
  now.getMinutes(),
  now.getSeconds(),
];

// no-restricted-syntax (hardcoded hex and numeric rgba in script)
export const scriptHex = "#a78bfa";
export const scriptRgba = "rgba(10, 132, 255, 0.5)";
</script>

<style scoped>
/* stylelint: color-no-hex + declaration-property-value-disallowed-list */
.canary-hex {
  color: #a78bfa;
}

.canary-numeric-rgba {
  background: rgba(10, 132, 255, 0.5);
  border-color: rgb(255, 0, 0);
}
</style>

import { computed, ref } from 'vue'

const 侧栏折叠 = ref(false)

export function use桌面布局状态() {
  function 切换侧栏折叠() { 侧栏折叠.value = !侧栏折叠.value }
  function 设置侧栏折叠(值: boolean) { 侧栏折叠.value = 值 }
  return {
    侧栏已折叠: computed(() => 侧栏折叠.value),
    切换侧栏折叠,
    设置侧栏折叠,
  }
}

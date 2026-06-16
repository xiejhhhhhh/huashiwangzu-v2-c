<template>
  <div class="主布局">
    <!-- 在 V1.5 中：当路由为 /desktop 时，由桌面壳接管全屏布局，隐藏传统侧边栏与顶部栏 -->
    <div v-if="当前路径 !== '/desktop'" class="侧边栏">
      <div class="侧边栏标题">华世王镞</div>
      <div class="侧边栏菜单">
        <el-menu :default-active="当前路径" router>
          <el-menu-item v-for="项 in 菜单" :key="项.路径" :index="项.路径">
            <el-icon><component :is="获取图标组件(项.图标)" /></el-icon>
            <span>{{ 项.名称 }}</span>
          </el-menu-item>
        </el-menu>
      </div>
    </div>

    <div class="主体区域">
      <div v-if="当前路径 !== '/desktop'" class="顶部栏">
        <div class="顶部栏左侧">
          <div class="通知按钮" @click="切换通知面板">
            <el-badge :value="未读数" :hidden="未读数 <= 0" class="通知角标">
              <el-icon :size="22"><Bell /></el-icon>
            </el-badge>
            <NoticePanel
              :显示="显示通知面板"
              :列表="通知列表"
              @标记已读="标记已读"
              @全部已读="全部已读"
            />
          </div>
        </div>
        <div class="顶部栏右侧">
          <el-button class="反馈按钮" type="primary" size="small" @click="显示反馈弹窗 = true">
            问题反馈
          </el-button>
           <FeedbackSubmitDialog :显示="显示反馈弹窗" @关闭="显示反馈弹窗 = false" @提交success="显示反馈弹窗 = false" />
          <el-dropdown trigger="click" @command="处理下拉">
            <span style="cursor: pointer; display: flex; align-items: center; gap: 8px;">
              <el-avatar :size="32" style="background: var(--主色);">
                {{ store.用户信息?.displayName?.charAt(0) || '?' }}
              </el-avatar>
              <span>{{ store.用户信息?.displayName || '用户' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="内容区">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, Bell } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/platform/stores/user'
import { use权限 } from '@/shared/composables/use-permission'
import NoticePanel from '@/shared/components/notification-panel.vue'
import FeedbackSubmitDialog from './feedback-submit-dialog.vue'
import { use通知 } from '@/shared/composables/use-notifications'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const 显示反馈弹窗 = ref(false)
const route = useRoute()
const store = useUserStore()
const 当前路径 = computed(() => route.path)
const { 未读数, 通知列表, 显示通知面板, 切换通知面板, 标记已读, 全部已读 } = use通知('.通知按钮')
const { 可访问菜单 } = use权限()

/** 全量菜单定义（来源唯一：前端硬编码，按角色过滤） */
const 全量菜单 = [
  { 名称: '桌面', 路径: '/desktop', 图标: 'Files' },
]

/** 按角色过滤后的可见菜单 */
const 菜单 = computed(() => 全量菜单.filter(项 => 可访问菜单(项)))

function 获取图标组件(name: string) {
  return (ElementPlusIconsVue as any)[name]
}

function 处理下拉(command: string) {
  if (command === 'logout') {
    ElMessageBox.confirm('确定退出登录？', '提示').then(() => {
      store.登出().finally(() => {
        window.location.replace('/')
      })
    }).catch(() => {})
  }
}
</script>

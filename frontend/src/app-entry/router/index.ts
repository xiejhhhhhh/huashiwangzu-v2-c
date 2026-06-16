import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/platform/stores/user'
import MainLayout from '@/app-entry/layouts/main-layout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: '登录',
      component: () => import('@/app-entry/pages/login/index.vue'),
    },
    {
      path: '/',
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: 'desktop',
          name: '桌面',
          component: () => import('@/desktop/shell/index.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const store = useUserStore()
  const 是登录页 = to.path === '/'

  if (!是登录页 && !store.已检查过 && !store.已登录) {
    await store.fetchCurrentUser()
  }

  if (to.matched.some((记录) => 记录.meta.requiresAuth) && !store.已登录) {
    return '/'
  }

  if (是登录页 && store.已登录) {
    return '/desktop'
  }

  return true
})

export default router

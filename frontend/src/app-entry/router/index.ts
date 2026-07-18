import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/platform/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'login',
      component: () => import('@/app-entry/pages/login/index.vue'),
    },
    {
      path: '/desktop',
      name: 'desktop',
      meta: { requiresAuth: true },
      component: () => import('@/desktop/shell/index.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const store = useUserStore()
  const isLoginPage = to.path === '/'

  if (!isLoginPage && !store.hasChecked && !store.isLoggedIn) {
    await store.fetchCurrentUser()
  }

  if (to.matched.some((record) => record.meta.requiresAuth) && !store.isLoggedIn) {
    return '/'
  }

  if (isLoginPage && store.isLoggedIn) {
    return '/desktop'
  }

  return true
})

export default router

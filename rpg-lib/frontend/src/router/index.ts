import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'browse',
      component: () => import('../views/LibraryBrowse.vue'),
    },
    {
      path: '/book/:id',
      name: 'book',
      component: () => import('../views/BookDetail.vue'),
      props: true,
    },
  ],
})

export default router

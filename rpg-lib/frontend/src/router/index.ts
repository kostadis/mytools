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
    {
      path: '/browse/:type',
      name: 'browse-index',
      component: () => import('../views/BrowseIndex.vue'),
      props: true,
    },
    {
      path: '/topic/:type/:name',
      name: 'topic',
      component: () => import('../views/TopicHub.vue'),
      props: true,
    },
    {
      path: '/graph',
      name: 'graph',
      component: () => import('../views/GraphView.vue'),
    },
  ],
})

export default router

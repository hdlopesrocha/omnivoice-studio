import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/',
      name: 'studio',
      component: () => import('./views/StudioView.vue'),
      meta: {
        title: 'Studio',
        subtitle: 'Turn text into speech in any voice you have trained.',
      },
    },
    {
      path: '/voices',
      name: 'voices',
      component: () => import('./views/VoicesView.vue'),
      meta: {
        title: 'Voices',
        subtitle: 'Train reusable voice profiles from a short reference clip.',
      },
    },
    {
      path: '/design',
      name: 'design',
      component: () => import('./views/DesignView.vue'),
      meta: {
        title: 'Voice design',
        subtitle: 'Describe a voice with words — no reference audio required.',
      },
    },
    {
      path: '/batch',
      name: 'batch',
      component: () => import('./views/BatchView.vue'),
      meta: {
        title: 'Batch',
        subtitle: 'Generate a list of paragraphs as separate audio files.',
      },
    },
    {
      path: '/jobs',
      name: 'jobs',
      component: () => import('./views/JobsView.vue'),
      meta: {
        title: 'Jobs',
        subtitle: 'Queued, running, and completed model jobs.',
      },
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('./views/HistoryView.vue'),
      meta: {
        title: 'History',
        subtitle: 'Every generation is stored locally in your Docker volume.',
      },
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('./views/AboutView.vue'),
      meta: {
        title: 'About',
        subtitle: 'Runtime details, local-first privacy, and responsible use.',
      },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import './style.css'

createApp(App).use(createPinia()).mount('#app')

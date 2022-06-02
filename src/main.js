import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import App from './App.vue'

import HomePage from './pages/HomePage.vue';
import FeaturesPage from './pages/FeaturesPage.vue';
import RoadMap from './pages/RoadMap.vue';

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
		{ path: '/', component: HomePage, name: 'Home', navbar: true},
    { path: '/features', component: FeaturesPage, name: 'Features', navbar: true},
    { path: '/development', component: RoadMap, name: 'Road Map', navbar: true}
	]
})

// 5. Create and mount the root instance.
const app = createApp(App)
// Make sure to _use_ the router instance to make the
// whole app router-aware.
app.use(router)

app.mount('#app')

<template>
  <nav class="blue darken-2">
    <div class="nav-wrapper">
      <ul id="nav-mobile" class="left hide-on-med-and-down">
       <li v-for="link in routes" :key="link.name" :class="$route.name===link.name ? 'active':''">
         <router-link :to="link.path">{{link.name}}</router-link>
       </li>
     </ul>
    </div>
  </nav>
  <div class="container">
    <router-view></router-view>
  </div>
</template>

<script>
import _ from 'lodash';

export default {
  data() {
    return {
      routes: _.filter(this.$router.options.routes, 'navbar')
    }
  }
}
</script>

<style lang="scss" src="materialize-css/sass/materialize.scss">
  /* global styles */
</style>

<style module scoped>
  /* Local router container styles */
</style>

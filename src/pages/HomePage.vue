<template lang="html">
	<div class="">
		<div class="row">

		</div>
		<div class="row">
			<div class="col s4 offset-s2 icon-align">
				<img class="beymax-icon" src="https://cdn.discordapp.com/app-icons/310283932341895169/13d8e56a58e628234d1229cba809c1cd.png" alt="">
			</div>
			<div class="col s6 valign-wrapper">
				<h1>Beymax</h1>
			</div>
		</div>
		<div class="row">
			<div class="s12 center-align">
				<p class="flow-text">A customizable Discord Bot and Command-focused bot-building API</p>
			</div>
		</div>
		<div class="row">
			<div class="col s4 offset-s2 tooltipped" data-tooltip="Coming soon" data-position="top">
				<router-link to="/" class="disabled waves-effect waves-light btn blue darken-2">Get Beymax for your Server</router-link>
			</div>
			<div class="col s4 tooltipped" data-tooltip="Coming soon" data-position="top">
				<router-link to="/" class="disabled waves-effect waves-light btn blue darken-2">Build your own bot using Beymax</router-link>
			</div>
		</div>
	</div>
</template>
<script>
import M from 'materialize-css';

export default {
	mounted() {
    M.Tooltip.init(this.$el.querySelectorAll('.tooltipped'));
  }
}
</script>

<style lang="css" scoped>
	img.beymax-icon {
		border: 1px solid black;
		border-radius: 50%;
	}

</style>

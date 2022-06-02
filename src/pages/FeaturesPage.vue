<template lang="html">
	<div class="">
		<div class="row">
			<div class="col s12 center-align">
				<h2>Beymax Bot Features</h2>
			</div>
		</div>
		<div class="row">
			<div class="col s12">
				<ul class="collapsible">
					<li v-for="item in features" :key="item.key">
						<div class="collapsible-header">
							{{ item.header }}
						</div>
						<div class="collapsible-body">
							<span>{{ item.body }}</span>
						</div>
					</li>
				</ul>
			</div>
		</div>
	</div>
</template>

<script>
import M from 'materialize-css';
import _ from 'lodash';

export default {
	data() {
		return {
			features: _.map(
				[
					{header: "Text-based Adventures", body: "Beymax can emulate old text games (in .z5 format) and run them through a text channel in your server! Let your members play through classic games like Zork and Adventure"},
					{header: "Server Economy", body: "Beymax can track token balances for all of your users. Tokens are awarded for various types of server engagement"},
					{header: "Community Polls", body: "Beymax can create reaction-based polls with live-updating vote counts. You can also create Twitch-style Gamba polls and let members bet server tokens on poll options"},
					{header: "Poker", body: "Beymax can run poker games such as Blackjack or Texas Hold'em"},
					{header: "Temporary Voice Channels", body: "Do you like to keep your server channel list clean? Beymax can create temporary voice channels for your users and then delete them later when the party's over!"},
					{header: "Birthday announcements", body: "Users can set their own birthdays and Beymax will make a server announcement on everyone's big day!"},
					{header: "Reminders", body: "Users can set a reminder and have Beymax ping a channel at a specified future date"},
					{header: "Advanced Admin Features", body: "Beymax provides a suite of administrative features, enabling your server mods to modify user token balances and even run commands on behalf of other users"},
					{header: "Rich permissions", body: "Beymax uses a cascading permissions system, similar to Discord itself, allowing your administrators to set lists of rules which apply to specific users and roles. Beymax uses intelligent permission bindings to prevent users from changing names to inherit different rules"},
					{header: "And Much More!", body: "Beymax has many other small features such as meme making, custom statuses, automatic reactions, and more!"}
				],
				// Map auto-assigns key values for you
				(value, index) => _.assign(value, {key: index})
			)
		}
	},

	mounted() {
		M.Collapsible.init(this.$el.querySelectorAll('.collapsible'), {accordion: true});
	}
}
</script>

<style lang="css" scoped>
</style>

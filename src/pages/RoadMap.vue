<template lang="html">
	<div class="">
		<div class="row">
			<div class="col s12 center-align">
				<h2>Future Development Roadmap</h2>
			</div>
		</div>
		<div class="row">
			<div class="col s12">
				<p class="flow-text">Beymax is still under active development. It started as a personal discord bot, and slowly evolved into a high-level
					wrapper to the discord.py API to ease my own development. However, as Beymax grew, original design decisions became serious
					constraints. The original intent as a single-server personal bot is a serious impediment to providing Beymax as a public bot
					for others to use. Over the coming months, I intend to slowly, and incrementally rebuild parts of the bot and API with the
					ultimate goal of making Beymax a fully-featured, modern, and public multi-server bot while also keeping the setup simple
					enough that it's still feasible for a small developer to build and deploy their own bot using Beymax's internal API.
					This page serves to document the roadmap from Beymax's current state to the end goal
				</p>
			</div>
		</div>
		<div class="row">
			<div class="col s12">
				<table>
					<thead>
						<tr>
							<th>Milestone</th>
							<th>Description</th>
							<th>Status</th>
						</tr>
					</thead>
						<tr v-for="item in milestones" :key="item.key">
							<td :class="item.complete?'completed grey-text':''">{{item.name}}</td>
							<td :class="item.complete?'completed grey-text':''">{{item.description}}</td>
							<td :class="item.complete?'completed grey-text':''">{{item.status}}</td>
						</tr>
					<tbody>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script>
import _ from 'lodash';
import {format as timeformat} from 'timeago.js';

export default {
	data() {
		return {
			milestones: _.map(
				[
					{name: "Dockerization", description: "Get Beymax to run in a Docker container. This makes deployment easier and paves the way for future sharding", status: "In progress. Estimated "+timeformat("2022-06-15")},
					{name: "Research and Replanning", description: "Research the sharded-paradigm for discord bots. Evaluate the pattern of a controller node vs other bot implementations", status: "In progress. Estimated "+timeformat("2022-07-01")},
					{name: "Controller Node", description: "Add a controller interface to the API and provide the current internal control logic and a new separate docker container as controller options. This centralizes responsibility for certain bot tasks such as registering commands", status: "Planned. Estimated "+timeformat("2022-10-01")},
					{name: "Automations", description: "Get automations running to: rebuild the docker image on any code change; build developer docs on code changes to core components; build end-user docs on code changes to bots", status: "Planned"},
					{name: "Better Database", description: "Add a database interface to the API and provide the current implementation plus a SQLite/MySQL implementation", status: "Planned"},
					{name: "Modern Commands", description: "Migrate to the modern client command system. Also work with command buttons etc", status: "Planned"},
					{name: "Modern Permissions", description: "Switch to the modern discord permissions system, allowing server admins to manage command permissions from their server settings", status: "Planned"},
					{name: "Purge Single-server mode", description: "Majorly overhaul control logic to allow Beymax to interact with multiple servers at once. This is the major blocker to public usage", status: "Planned"},
					{name: "Migrate future-dispatch to controller", description: "The future-dispatch event system should be centralized to the controller node", status: "Planned"},
					{name: "Public Hosting", description: "Migrate Beymax to new hosting and enable invites to other servers", status: "Planned"},
					{name: "Multisharding", description: "Enable multisharding, allowing the bot to scale as needed to fit demand", status: "Planned"},
					{name: "Controller Sync", description: "On boot, the controller node should audit the local bot code to determine capabilities and ensure that the discord API is in sync (ie: add/remove commands)", status: "Planned"}
				],
				// Map auto-assigns key values for you
				(value, index) => _.assign(value, {key: index})
			)
		}
	}
}
</script>

<style lang="css" scoped>
	.completed {
		text-decoration: line-through;

	}
</style>

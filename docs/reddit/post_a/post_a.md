# Post A -- website + Python simulator (Reddit draft)

Draft of the r/TheSilphArena launch post for the pogo-dives site
(https://mglerner.com/pogo-dives) and the gopvpsim simulator. The
`**[IMAGE: NN-...png]**` markers show where each screenshot in `images/` goes
in the Reddit post; they will be swapped to rendered `![]()` links here after
the post is live.

**Title:** I made a website that shows how all 4096 stack up against the meta, ported PvPoke's battle sim to Python, and a bunch of other stuff. Bonus: which Palkia-O/Dialga-O do I ETM?!

---

Big disclaimer: I'm kind of a filthy casual. I've never made it to Legend, but I love to play with data, and I definitely love playing PoGo PvP more than Niantic does, so here we are. I'm TitanTrainers15 in PoGo and on Discord, but I somehow have this username here. Oh well.

A long time ago, I saw [this post](https://www.reddit.com/r/TheSilphArena/comments/z11xr0/) by u/poops_all_berries, and thought it was awesome. I tried to replicate it myself, but I suck at JavaScript. Skip forward a couple of years, and I cheated by getting Claude to help me port PvPoke's (EmpoleonDynamite, [pvpoke.com](https://pvpoke.com)) battle engine to Python ([code on github](https://github.com/mglerner/gopvpsim)). I drifted a bit from those spectrum graphs, but I'm having a ton of fun and think it might be useful for other folks. I'd love feedback ... and even bug reports, since there are probably bugs.

## The graphs

The heart of the site is the graphs.

So, you get 4096 possible IV combinations (0/0/0, 0/0/1, ... 15/15/15). We take each of those and sim them against the meta. Then we plot them as points, with stat product on the x-axis and average battle score on the y-axis. The battles use the Python code, but the Battle Score is like PvPoke's. The default view is an average of all shield scenarios, and a score of 500 is an even fight. There are dropdowns to do specific shield scenarios, decide whether or not to bait, control what's on the y-axis, decide if you want to sim vs PvPoke default IVs or the rank 1, or sim with a different moveset.

Here's the [Tinkaton OUL](https://mglerner.com/pogo-dives/tinkaton-ultra-league/) graph.

**[IMAGE: 01-tinkaton-oul-spectrum.png -- Tinkaton OUL spectrum graph (WIDE). Insert/upload here.]**

I think this is really cool. You can look at the whole population at once instead of at a single matchup, and you can see a lot of patterns.

- Better stat product mostly means better performance (the graph has a positive slope)
- The band of points curves sharply down on the left, because TERRIBLE IVs are way worse than bad IVs. Similarly, it curves up more quickly at the right.
- I also think this graph is just pretty. It looks like a fern. Who doesn't love ferns.
- In blue, you can see the builds that got tagged as Ninetales Slayer. You can see the page for more detail, but those ones ride the top of the band, trading some bulk to get enough atk to beat Ninetales in the 2-0 (among other things).
- You can see the other pattern in pink, with Annihilape Bulk, which is losing some wins by trading atk for bulk ... but gaining enough bulk to flip some Annihilape matchups. Is that a tradeoff you want to make? WHO KNOWS! I'm not an expert, and certainly neither is my website. But it's cool to be able to see all of this at once.

On the website, you can

- Hover over any point to see a lot more detail
- Enter in your own mons' IVs (either via a PokeGenie export or by hand) to highlight them on the graph.
- Inspired by u/orgodemir's [post](https://www.reddit.com/r/TheSilphArena/comments/yxzg7f/), text in the website marks [Pareto-efficient](https://en.wikipedia.org/wiki/Pareto_efficiency) IVs with a crown emoji (👑). The graph marks them with whatever symbol ends up saying it's them in the legend. This is even better in my iPhone app (teaser ... post to come soon)

Here's another one, GL Mimikyu (with Thunder, so sue me, you'll have to go to the [website](https://mglerner.com/pogo-dives/mimikyu-great-league/) to see Play Rough)

**[IMAGE: 02-mimikyu-gl-spectrum.png -- GL Mimikyu spectrum graph, Thunder moveset (WIDE). Insert/upload here.]**

- You can see several more spreads that trade off for bulk. The Togekiss Bulk (purple) is really interesting because it shows up even on several really highly ranked mons.
- Check out that band on the right that sits below the main curve! Those are mons with high stat products that are WAY worse than other mons nearby!
- If you zoom in (easy to do on the website), you can also see that the stat-product rank 1 sits in that lower band, and is way worse than the rank 5. RyanSwag (u/RyanoftheDay) would be proud.

Last one: Stunfisk

**[IMAGE: 03-stunfisk-gl-spectrum.png -- Stunfisk GL spectrum graph (WIDE). Insert/upload here.]**

- I took a stab at auto-finding slayer builds (i.e. builds that beat other Stunfisks) You can see that those all have pretty low stat product/battle score (no surprise), but some are way better than others (easier to see on the website at full size ... or zoomed in which you can definitely do).
- I think this visual does a good job of showing you that there are a lot of high stat product builds that don't actually hit the bulkpoints you might want.
- It's also fun to see a couple of very unique spreads show up. Check the [site](https://mglerner.com/pogo-dives/stunfisk-great-league/) for more detail.

## Infographics

I love the infographics people post. I particularly thought the recent one DragapultSim and Lundberger ([link](https://x.com/lundberger/status/2067186798363574307)) put together for S-Corviknight was interesting. So, I made my dives try to auto-generate an infographic at the top. It'll never be as good as actual expert analysis, but I think it's pretty good! It even tells you what you gain/lose when comparing shadow to non-shadow.

**[IMAGE: 04-dive-infographic.png -- auto-generated dive infographic, Pokemon Dark theme, ~half screen width. Insert/upload here.]**

## The rest of the page

I LOVE RyanSwag (u/RyanoftheDay) and JRE47's (u/JRE47) deep dives, along with ones on HSH's discord. Those are actual expert-level posts. I'm just a filthy casual, so I didn't try to interpret it all, but the rest of the page does a few things

- Collects as much as I could about breakpoints, bulkpoints, etc.
- Groups things together into different thresholds. Probably not as good as the experts, but still pretty good ... especially when there's not an expert dive out yet, like for UL Mimikyu.
- Lets you switch between BB and cap-at-level-50.

## What to build for ML?

Super inspired by [XehrFelrose's Deep Dives](https://www.youtube.com/watch?v=6N3lXp39qtQ) here. I built this because we're getting the chance to ETM the move onto [Palkia-O](https://mglerner.com/pogo-dives/articles/palkia-origin-ml-iv-guide/) and [Dialga-O](https://mglerner.com/pogo-dives/articles/dialga-origin-ml-iv-guide/), and I wanted to know if I should ETM my 15/15/14 when I already have a 15/14/15. The page mostly does what Xehr's dive does, and makes a bunch of tables along the way. Probably too wordy, but it's a lot of dust/candy XL!

Again, I'm no expert, but I know those dives took Xehr FOREVER, and my script can just churn through the whole ML meta and then smart folks can interpret the results.

## Comparing builds

I then got curious about what things change ... but don't swing matchups. HSH is always saying stuff like "you really want X breakpoint because it lets you shield once and then farms all the way down, ending with 100 energy" or something super clever like that. So, all of the dives and ML pages have a section at the top where you can enter in a few specific spreads and compare them. Here's an example from Shadow Corviknight, comparing a 7/15/1 to an 0/13/14.

**[IMAGE: 05-scorviknight-compare-flips.png -- Shadow Corviknight compare widget, matchup-flips view (small). Insert/upload here.]**

**[IMAGE: 06-scorviknight-compare-closecalls.png -- Shadow Corviknight compare widget, close-calls detail, Kingdra + Empoleon lines (small). Insert/upload here.]**

You can see which matchups flip at the top. The second one shows you things like, in the Shadow-Kingdra 2-2, one build wins with 1 HP and no energy. The other has almost 60% HP left! Or, vs the Shadow Empoleon, one build wins with 3 HP and no energy, while the other wins with over half of its HP left, and almost halfway to an air cutter.

## Python simulator

For the nerds among you, you can get the python simulator (battle code, command line scripts, etc) on [github](https://github.com/mglerner/gopvpsim). So much of it is based on PvPoke, and the rest of this community gives so much away for free that I thought it would be ridiculous to do anything other than open source it with the MIT license. Hope it's useful to someone else! Oh, and since this really does rest so heavily on PvPoke, it's worth pointing out that I checked with him before releasing either the website or the github repo ... he's in favor of both :).

I didn't build a GUI because that's not really my use case, but I could look into it if someone wants. The [github site](https://github.com/mglerner/gopvpsim#divergences-from-pvpoke) documents the cases where I deviate from PvPoke ... but my BattleScore is almost exactly the same.

## Quick note on AI

I definitely used Claude heavily in this project. At first, because I needed the help regarding JS vs Python. But the analysis ideas, graph ideas, etc are all mine. If you're a real nerd, you can check the logs in the repo to see this was way more than "hey Claude, one-shot me something for karma."

I don't love it when people pass off AI work as their own, so I tried to make sure the site is super clear about what's AI generated, what's human generated, and what's a hybrid.

---

**Links**

- Site: https://mglerner.com/pogo-dives
- Code (repo): https://github.com/mglerner/gopvpsim
- GoBattleKit (companion iOS app): a separate post is coming, likely tomorrow. If I can still edit, I'll add the link here.

"""Seeded replay tests for Dragon Slayer II and Ellen training."""

from collections import defaultdict
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT=Path(__file__).resolve().parents[2]
Q='quest.dragon_slayer_ii'
CLAIM='claim.dragon_slayer_ii.ellen_training'
REWARD='reward.ds2.ellen_combat_training'
BRANCHES=('kharazi','morytania','ungael','kourend')


class DragonSlayerIITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts=Contracts(ROOT/'schemas')
        cls.catalog = load_catalog(ROOT / 'data/manifest.json', contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile=read_json(ROOT/'data/profiles/main-baseline.json')
        cls.batch_actions = read_json(ROOT / 'data/catalog/dragon-slayer-ii/actions.json')
        cls.actions = {action['id']: action for action in cls.batch_actions if action['kind'] != 'supply'}

    def seed(self,*,legends=True,cats=True,barbarian=True,levels=True,quest_points=200,
             map_pieces_extra=0,swamp_paste=10):
        initial={**self.profile['initial_state']}
        initial['xp_tenths']={name:100000000 if levels else 0 for name in initial['xp_tenths']}
        initial['completed_action_ids']=[
            'quest.dream_mentor.complete','quest.animal_magnetism.complete',
            'quest.ghosts_ahoy.complete','quest.bone_voyage.complete',
            'quest.client_of_kourend.complete',
        ]
        initial['flags']={**initial.get('flags',{}),
            'flag.quest.legends_quest.complete':legends,
            'flag.quest.a_tail_of_two_cats.complete':cats,
            'unlock.ancient_cavern':barbarian}
        initial['counters']={**initial['counters'],'token.quest_points':quest_points}
        initial['inventory']={**initial['inventory'],
            'item.catspeak_amulet_enchanted':1,'item.lunar_seal_of_passage':1,
            'item.oak_plank':8,'item.swamp_paste':swamp_paste,'item.iron_nails':12,
            'item.hammer':1,'item.saw':1,'item.tinderbox':1,
            'item.astral_rune':1,'item.goutweed':1,'item.pestle_and_mortar':1,
            'item.rfd.machete':1,'item.ghostspeak_amulet':1,'item.lit_candle':1,
            'item.ds2.cut_dragonstone':1,'item.molten_glass':2,
            'item.exiles_glassblowing_pipe':1,'item.spade':1,
            'item.fire_rune':21,'item.air_rune':15,'item.blood_rune':3,
            'item.ds2.map_piece':map_pieces_extra,
        }
        initial['location_id']='location.corsair_cove.landing'
        return RouteState(self.tables,self.profile['policies'],initial)

    def apply(self,state,action_id):
        record=self.tables['actions'][action_id]
        initial=state.snapshot();initial['location_id']=record['start_location_id']
        state=RouteState(self.tables,self.profile['policies'],initial)
        step={'kind':'action','action_id':action_id,'modeled_seconds':record['duration']['expected_seconds']}
        if 'planned_outcome' in record:step['planned_outcome']=record['planned_outcome']
        return state.apply(step,action_id)

    def route(self,state,*,stop_before=None):
        for action_id in self.actions:
            if action_id==stop_before:return state
            state=self.apply(state,action_id)
        return state

    def test_full_quest_rewards_and_one_time_ellen_training(self):
        state=self.route(self.seed())
        snap=state.snapshot()
        self.assertEqual(snap['counters']['token.quest_points'],205)
        for skill,amount in [('smithing',800000),('mining',600000),('agility',500000),('thieving',500000)]:
            self.assertEqual(snap['xp_tenths']['skill.'+skill],100000000+amount)
        for flag in ('unlock.ds2.myths_guild','unlock.ds2.vorkath_repeatable',
                     'unlock.ds2.speak_to_cats','unlock.ds2.lithkren_vault_dragons'):
            self.assertTrue(snap['flags'][flag])
        for key in BRANCHES:
            self.assertEqual(snap['inventory'].get('item.ds2.key_'+key,0),0)
        self.assertIn(Q+'.complete',snap['completed_action_ids'])
        self.assertEqual(snap['held_rewards'][0]['reward_id'],REWARD)
        self.assertEqual(snap['held_rewards'][0]['remaining_picks'],4)
        for turn in range(4):
            step={'kind':'reward_use','instance_id':REWARD+'.instance.1','reward_id':REWARD,
                  'skill_id':'skill.attack','gain_xp_tenths':250000,
                  'overrides_observed_skill_restriction':False}
            state=state.apply(step, 'ellen-pick-'+str(turn))
        self.assertEqual(state.snapshot()['xp_tenths']['skill.attack'],101000000)
        self.assertEqual(state.snapshot()['held_rewards'],[])
        with self.assertRaises(DataError):self.apply(state,CLAIM)

    def test_exact_quest_start_gates(self):
        for data in [self.seed(legends=False),self.seed(cats=False),self.seed(levels=False),
                     self.seed(quest_points=199)]:
            with self.assertRaises(DataError):self.apply(data,Q+'.start')
        gates=self.actions[Q+'.start']['requirements']['requirements']
        skills={r['skill_id']:r['minimum_level'] for r in gates if r['kind']=='skill'}
        self.assertEqual(skills,{
            'skill.magic':75,'skill.smithing':70,'skill.mining':68,'skill.crafting':62,
            'skill.agility':60,'skill.thieving':60,'skill.construction':50,'skill.hitpoints':50})
        self.assertTrue(all(not r['boostable'] for r in gates if r['kind']=='skill'))

    def test_five_independent_map_sources_total_twenty_four(self):
        producers=[a for a in self.actions.values() if any(e.get('item_id')=='item.ds2.map_piece' for e in a['effects'])]
        self.assertEqual(len(producers),5)
        self.assertEqual(sorted(e['quantity'] for a in producers for e in a['effects'] if e['item_id']=='item.ds2.map_piece'),[3,4,5,5,7])
        s=self.route(self.seed(),stop_before=Q+'.solve_lithkren_map')
        self.assertEqual(s.snapshot()['inventory']['item.ds2.map_piece'],24)
        s=self.apply(s,Q+'.solve_lithkren_map')
        self.assertEqual(s.snapshot()['inventory'].get('item.ds2.map_piece',0),0)

    def test_boat_materials_required_and_debited(self):
        s=self.route(self.seed(),stop_before=Q+'.build_rowboat')
        with self.assertRaises(DataError):
            self.apply(self.route(self.seed(swamp_paste=9),stop_before=Q+'.build_rowboat'),Q+'.build_rowboat')
        s=self.apply(s,Q+'.build_rowboat')
        self.assertEqual(s.snapshot()['inventory'].get('item.oak_plank',0),0)
        self.assertEqual(s.snapshot()['inventory'].get('item.swamp_paste',0),0)
        self.assertEqual(s.snapshot()['inventory'].get('item.iron_nails',0),0)
        self.assertTrue(s.snapshot()['flags']['unlock.ds2.lithkren_rowboat'])

    def test_all_four_key_pieces_needed_and_fire_wave_budget(self):
        s=self.route(self.seed(),stop_before=Q+'.reach_ancient_cavern')
        for key in BRANCHES:
            self.assertEqual(s.snapshot()['inventory'].get('item.ds2.key_'+key),1)
        missing=self.route(self.seed(barbarian=False),stop_before=Q+'.reach_ancient_cavern')
        with self.assertRaises(DataError):self.apply(missing,Q+'.reach_ancient_cavern')
        s=self.route(self.seed(),stop_before=Q+'.forge_dragon_key')
        self.assertEqual(s.snapshot()['inventory'].get('item.fire_rune',0),0)
        self.assertEqual(s.snapshot()['inventory'].get('item.air_rune',0),0)
        self.assertEqual(s.snapshot()['inventory'].get('item.blood_rune',0),0)
        s=self.apply(s,Q+'.forge_dragon_key')
        self.assertEqual(s.snapshot()['inventory']['item.ds2.dragon_key'],1)
        for key in BRANCHES:self.assertEqual(s.snapshot()['inventory'].get('item.ds2.key_'+key,0),0)

    def test_branch_independence_and_recruitment_join(self):
        for slug in ('enter_kharazi_maze','ask_reldo','ask_brundt','ask_amelia'):
            reqs=self.actions[Q+'.'+slug]['requirements']['requirements']
            self.assertEqual([r['action_id'] for r in reqs if r['kind']=='action_completed'],[Q+'.learn_four_keys'])
        reqs=self.actions[Q+'.war_council']['requirements']['requirements']
        self.assertEqual({r['action_id'] for r in reqs},
            {Q+'.recruit_amik',Q+'.recruit_lathas',Q+'.recruit_brundt'})

    def test_combat_failures_and_partial_rewards(self):
        for slug in ('defeat_spawn','defeat_robert','solve_kharazi_maze','track_swamp_key',
                     'ungael_lever','solve_crypt_statues','defeat_vorkath','defend_ship','galvek_phase_4'):
            self.assertIn('planned_outcome',self.actions[Q+'.'+slug])
        with self.assertRaises(DataError):self.apply(self.seed(),Q+'.complete')
        with self.assertRaises(DataError):self.apply(self.seed(),CLAIM)

    def test_reward_registry_and_non_prayer_eligible_skills(self):
        reward=self.tables['xp_rewards'][REWARD]
        self.assertEqual(reward['selection_count'],4)
        self.assertEqual(reward['amount']['xp_tenths'],250000)
        self.assertNotIn('skill.prayer',reward['eligible_skills'])
        self.assertFalse(reward['retainable'])
        raw=read_json(ROOT/'data/raw/build-242/reward-registry.json')['entries']
        pkg=next(x for x in raw if x['id']=='review.quest.dragon_slayer_ii.combat_training')
        self.assertEqual(pkg['status'],'collected')
        self.assertEqual(pkg['producer_action_id'],CLAIM)
        self.assertIn({'kind': 'action_completed', 'action_id': f'{Q}.complete'},
                      pkg['requires']['requirements'])

    def test_every_stage_is_reachable_from_the_main_baseline(self):
        unreachable = unreachable_records(self.catalog, self.profile)
        action_ids = {action['id'] for action in self.batch_actions}
        self.assertEqual(action_ids.intersection(unreachable['actions']), set())

    def test_instance_stages_enter_and_return_through_their_own_locations(self):
        for ingress, next_stage in (
            ('enter_dream', 'defeat_robert'),
            ('board_lithkren', 'read_aivas_diary'),
            ('enter_kharazi_maze', 'solve_kharazi_maze'),
            ('sail_ungael', 'defeat_vorkath'),
            ('enter_ungael_cave', 'ungael_lever'),
            ('enter_shayzien_crypt', 'solve_crypt_statues'),
            ('unlock_mithril_door', 'heat_dragon_head_1'),
            ('boat_to_assault', 'defend_ship'),
            ('defend_ship', 'defeat_green_blue'),
        ):
            origin, destination = self.actions[f'{Q}.{ingress}'], self.actions[f'{Q}.{next_stage}']
            self.assertNotEqual(origin['start_location_id'], origin['end_location_id'])
            self.assertEqual(origin['end_location_id'], destination['start_location_id'])
        self.assertEqual(self.actions[f'{Q}.defeat_robert']['end_location_id'], 'location.lunar_quests.brazier')
        self.assertEqual(self.actions[f'{Q}.track_swamp_key']['start_location_id'], 'location.mort_myre.north_gate')

    def test_travel_never_walks_across_continents(self):
        locs=self.tables['locations']
        all_edges=[e for e in self.tables['travel_edges'].values() if e['id'].startswith('travel.ds2.')]
        self.assertGreaterEqual(len(all_edges),40)
        for edge in all_edges:
            start=locs[edge['from_location_id']]
            end=locs[edge['to_location_id']]
            if edge['mode']=='walk':
                self.assertLess(max(abs(start['x']-end['x']),abs(start['y']-end['y'])),500)


if __name__=='__main__':unittest.main()

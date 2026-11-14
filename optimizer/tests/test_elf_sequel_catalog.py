"""Replay the Roving Elves/Mourning's End Part I quest chain and reward options."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT=Path(__file__).resolve().parents[2]
RO='quest.roving_elves'
ME='quest.mournings_end_part_i'


class ElfSequelCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts=Contracts(ROOT/'schemas')
        cls.tables=CatalogValidator(load_catalog(ROOT/'data/manifest.json',contracts),contracts).tables
        cls.profile=read_json(ROOT/'data/profiles/main-baseline.json')
        cls.actions=read_json(ROOT/'data/catalog/elf-sequel/actions.json')

    def seed(self, earlier=('quest.regicide.complete','quest.waterfall_quest.complete',
                            'quest.big_chompy_bird_hunting.complete','quest.sheep_herder.complete')):
        initial=deepcopy(self.profile['initial_state'])
        initial['completed_action_ids']=list(earlier)
        initial['inventory']['item.coins']=300_000
        initial['inventory']['item.glarials_pebble']=1
        initial['inventory']['item.glarials_amulet']=1
        initial['counters']['token.quest_points']=100
        for name in initial['xp_tenths']:
            initial['xp_tenths'][name]=20_000_000
        return RouteState(self.tables,self.profile['policies'],initial)

    def do(self,state,id):
        action=self.tables['actions'][id]
        snap=state.snapshot()
        snap['location_id']=action['start_location_id']
        state=RouteState(self.tables,self.profile['policies'],snap)
        step={'kind':'action','action_id':id,
              'modeled_seconds':action['duration']['expected_seconds']}
        if action.get('planned_outcome'):step['planned_outcome']=action['planned_outcome']
        return state.apply(step)

    def roving(self,state=None):
        state=state or self.seed()
        for action in self.actions:
            id=action['id']
            if id.startswith('quest.roving_elves.') and not id.startswith('quest.roving_elves.claim_'):
                state=self.do(state,id)
            elif id=='supply.roving.purchase_supplies':
                state=self.do(state,id)
        return state

    def mourning(self,state):
        for action in self.actions:
            if (action['id'].startswith('quest.mournings_end_part_i.') and
                action['id'] not in (ME+'.enter_mourner_base_no_pass',ME+'.talk_to_elena_no_apple')) or \
               action['id'] in ('supply.mep1.buy_infiltration_supplies',
                                 'supply.mep1.collect_tar_for_naphtha'):
                state=self.do(state,action['id'])
        return state

    def test_roving_quest_grants_fixed_xp_and_single_crystal_choice(self):
        state=self.roving()
        snap=state.snapshot()
        self.assertEqual(snap['counters']['token.quest_points'],101)
        self.assertEqual(snap['xp_tenths']['skill.strength'],20_100_000)
        self.assertTrue(snap['flags']['unlock.crystal_weapon_eligibility'])
        self.assertEqual(snap['inventory'].get('item.roving_enchanted_seed',0),0)
        bow=self.do(state,RO+'.claim_crystal_bow')
        self.assertEqual(bow.snapshot()['inventory']['item.roving_crystal_bow_500'],1)
        with self.assertRaises(DataError):
            self.do(bow,RO+'.claim_crystal_shield')
        shield=self.do(state,RO+'.claim_crystal_shield')
        self.assertEqual(shield.snapshot()['inventory']['item.roving_crystal_shield_500'],1)

    def test_mourning_quest_completes_using_produced_disguise_and_toads(self):
        state=self.mourning(self.roving())
        snap=state.snapshot()
        self.assertEqual(snap['counters']['token.quest_points'],103)
        self.assertEqual(snap['xp_tenths']['skill.thieving'],20_400_000)
        self.assertEqual(snap['xp_tenths']['skill.hitpoints'],20_250_000)
        self.assertTrue(snap['flags']['unlock.lletya_access'])
        self.assertTrue(snap['flags']['unlock.mep1_complete'])
        self.assertEqual(snap['inventory']['item.mep1_teleport_crystal_four'],1)
        self.assertEqual(snap['inventory'].get('item.mep1_toxic_powder',0),0)
        for colour in ('red','green','blue','yellow'):
            self.assertEqual(snap['inventory'].get('item.mep1_'+colour+'_toad',0),0)
        with self.assertRaises(DataError):
            self.do(state,ME+'.complete')

    def test_roving_prerequisites_gate_start(self):
        for missing in ('quest.regicide.complete','quest.waterfall_quest.complete'):
            earlier=[x for x in self.seed().snapshot()['completed_action_ids'] if x!=missing]
            with self.assertRaises(DataError):
                self.do(self.seed(earlier),RO+'.talk_to_islwyn')
        snap=self.seed().snapshot()
        snap['xp_tenths']['skill.agility']=0
        snap['flags']['unlock.port_tyras_charter']=True
        state=RouteState(self.tables,self.profile['policies'],snap)
        state=self.do(state,RO+'.talk_to_islwyn')
        self.assertIn(RO+'.talk_to_islwyn',state.snapshot()['completed_action_ids'])

    def test_mourning_prerequisites_and_material_gates(self):
        for missing in ('quest.big_chompy_bird_hunting.complete','quest.sheep_herder.complete'):
            state=self.roving(self.seed([x for x in self.seed().snapshot()['completed_action_ids'] if x!=missing]))
            with self.assertRaises(DataError):
                self.do(state,ME+'.talk_to_eluned_to_start')
        state=self.roving()
        snap=state.snapshot()
        snap['xp_tenths']['skill.ranged']=0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables,self.profile['policies'],snap),ME+'.talk_to_eluned_to_start')
        state=self.mourning(self.roving())
        self.assertTrue(state.snapshot()['flags']['unlock.mourner_hq_basement'])

    def test_naphtha_and_sheep_consumptions_cannot_be_skipped(self):
        state=self.roving()
        for action in self.actions:
            id=action['id']
            if id=='supply.mep1.buy_infiltration_supplies' or id=='supply.mep1.collect_tar_for_naphtha' or (
                id.startswith(ME+'.') and id not in (ME+'.enter_mourner_base_no_pass',ME+'.talk_to_elena_no_apple')):
                if id==ME+'.get_naphtha':
                    snap=state.snapshot()
                    snap['inventory']['item.coal']=0
                    with self.assertRaises(DataError):
                        self.do(RouteState(self.tables,self.profile['policies'],snap),id)
                if id==ME+'.shoot_green_toad':
                    snap=state.snapshot()
                    snap['inventory']['item.mep1_green_toad']=0
                    with self.assertRaises(DataError):
                        self.do(RouteState(self.tables,self.profile['policies'],snap),id)
                state=self.do(state,id)

    def test_lletya_teleports_consume_two_of_four_crystal_charges(self):
        state=self.roving()
        state=self.do(state,ME+'.talk_to_eluned_to_start')
        state=self.do(state,ME+'.talk_to_arianwyn')
        self.assertEqual(state.snapshot()['counters']['token.mep1_teleport_charges'],4)
        edges=self.tables['travel_edges']
        teleports=[e for e in edges.values() if e['id'].startswith('travel.elf_sequel.') and
                   e['mode']=='teleport_item' and e['to_location_id'] in (
                       'location.mep1.talk_to_oronwen','location.mep1.return_to_arianwyn')]
        self.assertEqual(len(teleports),2)
        for left,edge in zip((3,2),teleports):
            snap=state.snapshot()
            snap['location_id']=edge['from_location_id']
            state=RouteState(self.tables,self.profile['policies'],snap)
            state=state.apply({'kind':'travel','edge_id':edge['id'],
                               'modeled_seconds':edge['duration']['expected_seconds']})
            self.assertEqual(state.snapshot()['location_id'],edge['to_location_id'])
            self.assertEqual(state.snapshot()['counters']['token.mep1_teleport_charges'],left)


if __name__=='__main__':unittest.main()

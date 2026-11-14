"""Focused draft replay for Regicide's stages, materials and rewards."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = 'quest.regicide'


class RegicideCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / 'schemas')
        cls.tables = CatalogValidator(load_catalog(ROOT / 'data/manifest.json', contracts), contracts).tables
        cls.profile = read_json(ROOT / 'data/profiles/main-baseline.json')
        cls.actions = read_json(ROOT / 'data/catalog/regicide/actions.json')

    def seed(self, completed=('quest.underground_pass.complete',), agility_xp=20_000_000):
        initial = deepcopy(self.profile['initial_state'])
        initial['completed_action_ids'] = list(completed)
        initial['inventory']['item.coins'] = 200_000
        initial['counters']['token.quest_points'] = 100
        for skill in initial['xp_tenths']:
            initial['xp_tenths'][skill] = 20_000_000
        initial['xp_tenths']['skill.agility'] = agility_xp
        initial['flags']['unlock.well_of_voyage'] = 'quest.underground_pass.complete' in completed
        return RouteState(self.tables, self.profile['policies'], initial)

    def at(self, state, location):
        snap = state.snapshot()
        snap['location_id'] = location
        return RouteState(self.tables, self.profile['policies'], snap)

    def do(self, state, action_id):
        action = self.tables['actions'][action_id]
        state = self.at(state, action['start_location_id'])
        step = {'kind': 'action', 'action_id': action_id,
                'modeled_seconds': action['duration']['expected_seconds']}
        if action.get('planned_outcome'):
            step['planned_outcome'] = action['planned_outcome']
        return state.apply(step)

    def replay(self):
        state = self.seed()
        for action in self.actions:
            state = self.do(state, action['id'])
        return state

    def test_full_route_awards_rewards_and_consumes_bomb(self):
        state = self.replay()
        snap = state.snapshot()
        self.assertIn(QUEST + '.complete', snap['completed_action_ids'])
        self.assertEqual(snap['counters']['token.quest_points'], 103)
        self.assertEqual(snap['xp_tenths']['skill.agility'], 20_137_500)
        self.assertEqual(snap['inventory']['item.coins'], 130_000)
        self.assertEqual(snap['inventory'].get('item.regicide_barrel_bomb', 0), 0)
        self.assertEqual(snap['inventory'].get('item.regicide_iorwerth_letter', 0), 0)
        self.assertEqual(snap['inventory'].get('item.regicide_crystal_pendant', 0), 0)
        self.assertEqual(snap['inventory']['item.coal'], 10)
        for unlock in ('unlock.arandar_overpass', 'unlock.regicide_catapult_destroyed',
                       'unlock.tirannwn_access', 'unlock.port_tyras_charter',
                       'unlock.dragon_halberd_equipping',
                       'unlock.iorwerth_camp_teleport_scrolls',
                       'unlock.zul_andra_teleport_scrolls', 'unlock.bjs_fairy_ring',
                       'unlock.gwenith_glide_attempt'):
            self.assertTrue(snap['flags'][unlock], unlock)
        with self.assertRaises(DataError):
            self.do(state, QUEST + '.complete')

    def test_start_requires_underground_pass_and_skills(self):
        state = self.do(self.seed(()), QUEST + '.go_to_ardougne_castle_floor2')
        with self.assertRaises(DataError):
            self.do(state, QUEST + '.talk_to_king_lathas')
        state = self.seed()
        state = self.do(state, QUEST + '.go_to_ardougne_castle_floor2')
        snap = state.snapshot()
        snap['xp_tenths']['skill.agility'] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile['policies'], snap),
                    QUEST + '.talk_to_king_lathas')
        snap['xp_tenths']['skill.agility'] = 20_000_000
        snap['xp_tenths']['skill.crafting'] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile['policies'], snap),
                    QUEST + '.talk_to_king_lathas')

    def test_cannot_distil_without_coal_or_fire_bomb_without_rabbit(self):
        state = self.seed()
        for action in self.actions:
            if action['id'] == QUEST + '.operate_still':
                snap = state.snapshot()
                snap['inventory']['item.coal'] = 0
                with self.assertRaises(DataError):
                    self.do(RouteState(self.tables, self.profile['policies'], snap), action['id'])
            if action['id'] == QUEST + '.use_rabbit_on_guard':
                snap = state.snapshot()
                snap['inventory']['item.regicide_cooked_rabbit'] = 0
                with self.assertRaises(DataError):
                    self.do(RouteState(self.tables, self.profile['policies'], snap), action['id'])
            state = self.do(state, action['id'])

    def test_early_charter_not_unlocked_and_return_route_exists(self):
        state = self.seed()
        for action in self.actions:
            if action['id'] == QUEST + '.return_to_tirannwn':
                snap = state.snapshot()
                self.assertFalse(snap['flags'].get('unlock.port_tyras_charter', False))
                self.assertFalse(snap['flags'].get('unlock.arandar_overpass', False))
                edges = self.tables['travel_edges']
                self.assertTrue(any(edge['id'].startswith('travel.regicide.') and
                                    edge['to_location_id'] == 'location.regicide.enter_tyras_camp' and
                                    edge['mode'] == 'other' for edge in edges.values()))
            state = self.do(state, action['id'])

    def test_rimmington_teleport_and_underground_pass_return_edges(self):
        edges = list(self.tables['travel_edges'].values())
        outbound = next(edge for edge in edges if edge['id'].startswith('travel.regicide.') and
                        edge['from_location_id'] == 'location.regicide.camp_furnace' and
                        edge['to_location_id'] == 'location.regicide.talk_to_chemist')
        self.assertEqual(outbound['mode'], 'teleport_item')
        state = self.seed()
        snap = state.snapshot()
        snap['inventory']['item.falador_teleport_tablet'] = 1
        snap['location_id'] = outbound['from_location_id']
        state = RouteState(self.tables, self.profile['policies'], snap)
        state = state.apply({'kind': 'travel', 'edge_id': outbound['id'],
                             'modeled_seconds': outbound['duration']['expected_seconds']})
        self.assertEqual(state.snapshot()['location_id'], outbound['to_location_id'])
        self.assertEqual(state.snapshot()['inventory'].get('item.falador_teleport_tablet', 0), 0)

        cave_return = next(edge for edge in edges if edge['id'].startswith('travel.regicide.') and
                           edge['mode'] == 'other' and
                           edge['to_location_id'] == 'location.regicide.enter_tyras_camp')
        state = self.at(state, cave_return['from_location_id'])
        state = state.apply({'kind': 'travel', 'edge_id': cave_return['id'],
                             'modeled_seconds': cave_return['duration']['expected_seconds']})
        self.assertEqual(state.snapshot()['location_id'], 'location.regicide.enter_tyras_camp')
        self.assertFalse(state.snapshot()['flags'].get('unlock.port_tyras_charter', False))


if __name__ == '__main__':
    unittest.main()

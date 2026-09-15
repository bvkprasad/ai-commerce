import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ai_commerce.ingestion import load_catalog, Catalog
from ai_commerce.service import CommerceService
from ai_commerce.domain import Request, paise

NOW=datetime(2026,9,15,tzinfo=timezone.utc)
ROOT=Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.catalog=load_catalog(now=NOW)
        self.service=CommerceService(self.catalog,clock=lambda:NOW)
        self.wifi={'category':'washing_machine','features':{'built_in_wifi':True}}
        self.dock=json.loads((ROOT/'examples/dual_monitor_dock.json').read_text())

    def ids(self, request):
        return [c['product_id'] for c in self.service.discover(request)['cards']]

    def test_wifi(self):
        self.assertEqual(self.ids(self.wifi),['wash-connect'])

    def test_verified_false_not_unknown(self):
        request={'category':'washing_machine','features':{'built_in_wifi':False}}
        self.assertEqual(set(self.ids(request)),{'wash-basic','wash-addon'})

    def test_conflicting_evidence(self):
        product=self.catalog.products['wash-connect']
        fact=copy.deepcopy(product['facts'][0]);fact['value']=False
        product['facts'].append(fact)
        self.assertEqual(self.ids(self.wifi),[])

    def test_withdrawal(self):
        self.catalog.sources['wash-connect-manual-v1']['active']=False
        self.assertEqual(self.ids(self.wifi),[])

    def test_wrong_product_evidence_rejected(self):
        data=json.loads((ROOT/'ai_commerce/data/catalog.json').read_text())
        data['products'][0]['facts'][0]['evidence']=['wash-basic-manual-v1']
        with self.assertRaises(ValueError): Catalog(data)

    def test_unknown_feature_rejected(self):
        with self.assertRaises(ValueError): self.service.discover({'features':{'magic':True}})

    def test_boolean_is_not_integer_budget(self):
        with self.assertRaises(ValueError): self.service.discover({'budget_paise':True})

    def test_exact_dock_fixture(self):
        result=self.service.discover(self.dock)
        self.assertEqual([c['product_id'] for c in result['cards']],['dock-d'])
        self.assertEqual(result['cards'][0]['commerce']['total_paise'],920000)
        excluded={x['product_id']:x for x in result['excluded']}
        self.assertEqual(excluded['dock-a']['compatibility']['status'],'UNSUPPORTED')
        self.assertEqual(excluded['dock-b']['compatibility']['status'],'UNSUPPORTED')
        self.assertEqual(excluded['dock-c']['commerce']['status'],'INELIGIBLE')
        self.assertEqual(excluded['dock-e']['compatibility']['status'],'UNKNOWN')

    def test_driver_permission_not_installation(self):
        self.dock['configuration']['driver_allowed']=True
        result=self.service.discover(self.dock)
        dock_b=next(x for x in result['excluded'] if x['product_id']=='dock-b')
        self.assertEqual(dock_b['compatibility']['status'],'CONDITIONAL')
        self.dock['configuration']['driver_installed']=True
        self.assertIn('dock-b',self.ids(self.dock))

    def test_revision_not_inferred(self):
        self.dock['configuration']['host']='L42-r1'
        self.assertEqual(self.ids(self.dock),[])

    def test_cables_must_match_offer(self):
        self.catalog.offers['dock-d']['cable_set']='other'
        self.assertEqual(self.ids(self.dock),[])

    def test_delivery_deadline(self):
        self.wifi['delivery_by']=(NOW+timedelta(hours=10)).isoformat()
        self.assertEqual(self.ids(self.wifi),[])

    def test_offer_expiry(self):
        self.service.clock=lambda:NOW+timedelta(minutes=30)
        self.assertEqual(self.ids(self.wifi),[])

    def test_out_of_stock(self):
        self.catalog.offers['wash-connect']['stock']=0
        self.assertEqual(self.ids(self.wifi),[])

    def test_missing_offer(self):
        del self.catalog.offers['wash-connect']
        self.assertEqual(self.ids(self.wifi),[])

    def test_smart_clarification(self):
        self.assertEqual(self.service.discover({'query':'Find an AC with smart control'})['status'],'CLARIFICATION')

    def test_unknown_query_constraint(self):
        result=self.service.discover({'query':'Find a washing machine with built-in wifi and quiet spin'})
        self.assertEqual(result['status'],'CLARIFICATION')
        self.assertIn('quiet spin',' '.join(result['questions']))

    def test_query_parsing(self):
        self.assertEqual(self.ids({'query':'Find a washing machine with built-in Wi-Fi under INR 40,000'}),['wash-connect'])

    def test_negation_clarifies(self):
        self.assertEqual(self.service.discover({'query':'washing machine without built-in wifi'})['status'],'CLARIFICATION')

    def test_prerequisites(self):
        request={'category':'ac','features':{'app_control':True}}
        self.assertEqual(self.ids(request),['ac-connect'])
        request['confirmed_prerequisites']=['external_bridge']
        self.assertEqual(set(self.ids(request)),{'ac-connect','ac-bridge'})

    def test_compare_unknown(self):
        products=self.service.compare(['wash-basic','wash-pending'])['products']
        self.assertIs(products[0]['features']['built_in_wifi']['value'],False)
        self.assertEqual(products[1]['features']['built_in_wifi']['status'],'UNKNOWN')

    def test_render_validation(self):
        card=self.service.discover(self.wifi)['cards'][0]
        card['commerce']['total_paise']=1
        with self.assertRaises(ValueError):
            self.service.validate_card(card,Request.parse(self.wifi,self.catalog.ontology),NOW)

    def test_graph_provenance_path(self):
        edge=next(target for relation,target in self.catalog.graph.edges['product:wash-connect'] if relation=='HAS_FEATURE')
        self.assertEqual(self.catalog.graph.edges[edge],[('SUPPORTED_BY','source:wash-connect-manual-v1')])

    def test_money(self):
        self.assertEqual(paise('9200.25'),920025)
        for bad in ['NaN','Infinity','1.001','-1']:
            with self.assertRaises(ValueError): paise(bad)

    def test_missing_citation_rejected(self):
        card=self.service.discover(self.wifi)['cards'][0]
        card['evidence']={}
        with self.assertRaises(ValueError):
            self.service.validate_card(card,Request.parse(self.wifi,self.catalog.ontology),NOW)

    def test_external_catalog_does_not_refresh_offers(self):
        catalog=load_catalog(ROOT/'ai_commerce/data/catalog.json',now=NOW+timedelta(days=1))
        service=CommerceService(catalog,clock=lambda:NOW+timedelta(days=1))
        self.assertEqual(service.discover(self.wifi)['cards'],[])

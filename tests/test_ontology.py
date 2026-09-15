import unittest
from ai_commerce.ontology import Ontology, Definition, Proposal


class OntologyTests(unittest.TestCase):
    def test_review_required(self):
        ontology=Ontology()
        with self.assertRaises(ValueError): ontology.approve(Proposal(1,Definition('energy_metering',bool,'Measured energy')))

    def test_approved_addition(self):
        ontology=Ontology()
        ontology.approve(Proposal(1,Definition('energy_metering',bool,'Measured energy'),'Demo reviewer'))
        self.assertEqual(ontology.version,2)
        ontology.validate('energy_metering',True)
        with self.assertRaises(ValueError): ontology.validate('energy_metering',1)

    def test_stale_proposal(self):
        ontology=Ontology()
        ontology.approve(Proposal(1,Definition('energy_metering',bool,'Measured energy'),'Reviewer'))
        with self.assertRaises(ValueError): ontology.approve(Proposal(1,Definition('other',str,'Other'),'Reviewer'))

    def test_no_overwriting(self):
        with self.assertRaises(ValueError):
            Ontology().approve(Proposal(1,Definition('built_in_wifi',str,'Changed meaning'),'Reviewer'))

    def test_demo_backfills_and_rebuilds(self):
        from ai_commerce.ontology import demo
        result=demo()
        self.assertEqual(result['backfilled_products'],['wash-connect'])
        self.assertTrue(result['regression']['wifi_value_preserved'])
        self.assertEqual(result['retrieval'][0]['product_id'],'wash-connect')

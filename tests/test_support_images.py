"""Support screenshots stay private and are normalized before storage."""
import base64
import io
import unittest
from PIL import Image
from tests import test_business


class SupportImageTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def screenshot(self):
        output = io.BytesIO()
        Image.new('RGB', (50, 30), 'white').save(output, 'PNG')
        return {'name': 'Снимок экрана.png', 'data_url': 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()}

    def test_images_are_verified_stored_with_the_message_and_private(self):
        owner, _ = self.account('screenshot-owner')
        other, _ = self.account('screenshot-other')
        status, ticket = self.call('/support', 'POST', {'message': 'Ошибка на экране', 'attachments': [self.screenshot()]}, owner)
        self.assertEqual(status, 201, ticket)
        self.assertTrue(ticket['needs_human'])
        uri = '/support/threads/'+ticket['ticket_id']+'/messages'
        status, result = self.call(uri, token=owner)
        self.assertEqual(status, 200, result)
        images = result['messages'][0]['metadata']['attachments']
        self.assertTrue(images[0]['data_url'].startswith('data:image/webp;base64,'))
        self.assertEqual(images[0]['name'], 'Снимок экрана.png')
        self.assertEqual(self.call(uri, token=other)[0], 403)
        self.assertEqual(self.call(uri)[0], 401)
        self.assertEqual(self.call(uri, 'POST', {'attachments': [self.screenshot()]}, owner)[0], 201)

    def test_invalid_images_do_not_create_a_ticket(self):
        token, _ = self.account('invalid-screenshot')
        for images in ([{'name': 'x.svg', 'data_url': 'data:image/svg+xml;base64,PHN2Zy8+'}],
                       [{'data_url': 'data:image/png;base64,YmFkLWltYWdl'}], [self.screenshot()]*4):
            self.assertEqual(self.call('/support', 'POST', {'message': 'Вопрос', 'attachments': images}, token)[0], 400)
        self.assertEqual(self.call('/support/threads', token=token)[1]['threads'], [])

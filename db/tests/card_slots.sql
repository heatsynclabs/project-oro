-- Card slots are EEPROM addresses on the door controller, not surrogate keys.
\pset pager off
SET client_min_messages = notice;

CALL t.must_fail('slot 200, which corrupts the controller alarm state',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B2',200)$$,
  'controller_slot_is_addressable');

CALL t.must_fail('slot 9, reserved for testing by the Access Card Procedure',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B3',9)$$,
  'controller_slot_is_addressable');

CALL t.must_fail('a lowercase tag, which would defeat the reconciler diff',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000a1b4',20)$$,
  'tag_is_normalised_hex');

CALL t.must_fail('a tag longer than the controller reads',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B4FF',21)$$,
  'tag_is_normalised_hex');

CALL t.must_pass('a card at slot 10, the lowest assignable',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B5',10)$$);

CALL t.must_pass('a card at slot 199, the highest addressable',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B6',199)$$);

CALL t.must_fail('two cards in one slot',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B7',199)$$,
  'cards_controller_slot_key');

CALL t.must_fail('two active cards with the same tag',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B5',30)$$,
  'cards_active_tag');

CALL t.must_pass('deactivating a card',
  $$UPDATE cards SET active=false, revoked_at=now(), revoked_reason='lost'
     WHERE tag_number='0000A1B5'$$);

CALL t.must_pass('reissuing a tag after the old card is deactivated',
  $$INSERT INTO cards (tag_number,controller_slot) VALUES ('0000A1B5',30)$$);

CALL t.must_fail('a revoked card that is still active',
  $$INSERT INTO cards (tag_number,controller_slot,active,revoked_at,revoked_reason)
    VALUES ('0000A1B8',31,true,now(),'lost')$$,
  'revoked_cards_are_inactive');

CALL t.must_pass('a card with no slot yet, issued but not provisioned',
  $$INSERT INTO cards (tag_number) VALUES ('0000A1B9')$$);

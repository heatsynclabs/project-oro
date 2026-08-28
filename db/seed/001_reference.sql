-- Reference data. Values with a governance source carry a citation.
BEGIN;

INSERT INTO tiers (id,name,monthly_cents,sort_order,card_eligible,storage) VALUES
  ('none','None',0,0,false,NULL),
  ('unable','Unable',0,1,false,NULL),
  ('volunteer','Volunteer',0,2,false,NULL),
  ('associate','Associate',2500,3,false,NULL),
  ('basic','Basic',5000,4,true,'bankers box'),
  ('plus','Plus',10000,5,true,'lockable locker');

INSERT INTO roles (id,name,description,grants_roles) VALUES
  ('admin','Admin','Manages members, cards, and roles',true),
  ('accountant','Accountant','Records and reconciles payments',false),
  ('board','Board member','Elected officer',false),
  ('operations','Operations','Runs the space day to day',false),
  ('host','Host','Hosts open hours. May check waiver status',false);

INSERT INTO governance_parameters (key,value,unit,source,effective) VALUES
  ('card_access.quorum','5','card members',
   'Bylaws, CARD ACCESS: minimum five card members present','2025-03-01'),
  ('card_access.notice_days','14','days',
   'Bylaws, CARD ACCESS: proposal posted at least two weeks ahead','2025-03-01'),
  ('card_access.tenure_months','2','months',
   'Membership vote replacing the board six month figure. DATE UNCONFIRMED: two research passes disagree (2025-05-22 against 2025-12-13). Both agree the value is two months. Check the bylaws page history.','2025-05-22'),
  ('card_access.min_tier','"basic"',NULL,
   'Bylaws, CARD ACCESS: paying member at the $50 level or higher','2025-03-01'),
  ('card_access.mentorship_months','6','months',
   'Bylaws, CARD ACCESS: nominator is mentor and responsible party','2025-03-01');

COMMIT;

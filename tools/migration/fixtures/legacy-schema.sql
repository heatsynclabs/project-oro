-- The legacy tables, in a schema of their own, so a migration can read
-- them beside the new ones inside one transaction.
--
-- Taken with pg_dump --schema-only from a replica of the legacy
-- application running its own db/schema.rb on postgres 9.6, and rewritten
-- into the legacy schema. Nothing here is hand transcribed.
-- tools/migration/README.md says how to regenerate it.

CREATE SCHEMA IF NOT EXISTS legacy;

CREATE TABLE legacy.cards (
    id integer NOT NULL,
    card_number character varying(255),
    card_permissions integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    user_id integer,
    name character varying(255)
);
CREATE SEQUENCE legacy.cards_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE legacy.cards_id_seq OWNED BY legacy.cards.id;
CREATE TABLE legacy.users (
    id integer NOT NULL,
    name character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    email character varying(255) DEFAULT ''::character varying NOT NULL,
    encrypted_password character varying(255) DEFAULT ''::character varying NOT NULL,
    reset_password_token character varying(255),
    reset_password_sent_at timestamp without time zone,
    remember_created_at timestamp without time zone,
    sign_in_count integer DEFAULT 0,
    current_sign_in_at timestamp without time zone,
    last_sign_in_at timestamp without time zone,
    current_sign_in_ip character varying(255),
    last_sign_in_ip character varying(255),
    admin boolean,
    member integer,
    waiver timestamp without time zone,
    orientation timestamp without time zone,
    emergency_name character varying(255),
    emergency_phone character varying(255),
    emergency_email character varying(255),
    member_level integer,
    payment_method character varying(255),
    phone character varying(255),
    current_skills text,
    desired_skills text,
    instructor boolean,
    hidden boolean,
    marketing_source text,
    payee character varying(255),
    accountant boolean,
    exit_reason text,
    twitter_url character varying(255),
    facebook_url character varying(255),
    github_url character varying(255),
    website_url character varying(255),
    email_visible boolean,
    phone_visible boolean,
    postal_code character varying(255),
    oriented_by_id integer
);
CREATE SEQUENCE legacy.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE legacy.users_id_seq OWNED BY legacy.users.id;
ALTER TABLE ONLY legacy.cards ALTER COLUMN id SET DEFAULT nextval('legacy.cards_id_seq'::regclass);
ALTER TABLE ONLY legacy.users ALTER COLUMN id SET DEFAULT nextval('legacy.users_id_seq'::regclass);
ALTER TABLE ONLY legacy.cards
    ADD CONSTRAINT cards_pkey PRIMARY KEY (id);
ALTER TABLE ONLY legacy.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
CREATE UNIQUE INDEX index_users_on_email ON legacy.users USING btree (email);
CREATE UNIQUE INDEX index_users_on_reset_password_token ON legacy.users USING btree (reset_password_token);

CREATE ROLE pega
    LOGIN
    PASSWORD 'rules';

ALTER DATABASE pega
    OWNER TO pega;

GRANT USAGE ON SCHEMA sqlj TO pega;
GRANT USAGE ON LANGUAGE java TO pega;

CREATE SCHEMA rules
    AUTHORIZATION pega;

GRANT ALL ON SCHEMA rules TO pega;

CREATE SCHEMA data
    AUTHORIZATION pega;

GRANT ALL ON SCHEMA data TO pega;

ALTER ROLE pega IN DATABASE pega
    SET search_path TO rules, data;

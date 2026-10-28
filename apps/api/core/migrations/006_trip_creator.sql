-- Only its maker may change a trip that has no owner (P11): a one-way key of the browser, chat or account.
ALTER TABLE trips ADD COLUMN IF NOT EXISTS creator text;

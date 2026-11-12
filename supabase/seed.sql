-- Dati iniziali: siti autorizzati e i 10 prodotti del prototipo (16 varianti/EAN)
-- Fonte prodotti: Shopify Face D, 12/11/2026. Prezzo di riferimento = prezzo su faced.com.

insert into public.sites (code, name, domain, authorized, kind) values
  ('atida',   'Atida (eFarma)', 'efarma.com',    true, 'retailer'),
  ('redcare', 'Redcare',        'redcare.it',    true, 'retailer'),
  ('benu',    'BENU Farma',     'benufarma.it',  true, 'retailer'),
  ('douglas', 'Douglas',        'douglas.it',    true, 'retailer'),
  ('sephora', 'Sephora',        'sephora.it',    true, 'retailer'),
  ('pinalli', 'Pinalli',        'pinalli.it',    true, 'retailer'),
  ('amazon',  'Amazon.it',      'amazon.it',     true, 'amazon')
on conflict (code) do update
  set name = excluded.name, domain = excluded.domain,
      authorized = excluded.authorized, kind = excluded.kind;

insert into public.products (ean, sku, name, variant, handle, rrp) values
  ('8057741882466','FD600F52091','CC Cream compatta correttrice 8,5 g','Light','cc-cream-compatta-correttrice-del-colore',22.50),
  ('8057741882473','FD600F52092','CC Cream compatta correttrice 8,5 g','Medium','cc-cream-compatta-correttrice-del-colore',22.50),
  ('8057741882480','FD600F52093','CC Cream compatta correttrice 8,5 g','Caramel','cc-cream-compatta-correttrice-del-colore',22.50),
  ('8057741880189','FD6004020','Crema contorno occhi anti-occhiaie','Chiara','face-d-crema-contorno-occhi-anti-occhiaie',25.00),
  ('8057741881438','FD600E21015','Crema contorno occhi anti-occhiaie','Scura','face-d-crema-contorno-occhi-anti-occhiaie',25.00),
  ('8057741880950','6021050FD','Crema viso e collo Instant Rich 50 ml',null,'face-d-crema-antieta-instant-rich',36.00),
  ('8057741880851','FD6020030','Pure Plump HA4 siero acido ialuronico','30 ml','face-d-pure-plump-ha4-acido-ialuronico',29.50),
  ('8057741881322','FD6030050','Pure Plump HA4 siero acido ialuronico','50 ml','face-d-pure-plump-ha4-acido-ialuronico',40.00),
  ('8057741880165','FD6002040','CC Cream SPF20 effetto naturale 40 ml','Light','face-d-cc-cream-crema-correttrice-colore',21.50),
  ('8057741880172','FD6003040','CC Cream SPF20 effetto naturale 40 ml','Medium','face-d-cc-cream-crema-correttrice-colore',21.50),
  ('8057741880806','FD6006040','CC Cream SPF20 effetto naturale 40 ml','Caramel','face-d-cc-cream-crema-correttrice-colore',21.50),
  ('8057741880998','6024030FD','Pure Lift siero collagene ed elastina',null,'face-d-pure-lift-elastina-collagene',29.50),
  ('8057741881445','FD600F23016','Siero Pure Plump + Vitamina C 16%','4 fiale','pure-c-trattamento-vitamina-c',48.00),
  ('8057741881162','FD7003015','Integratore Pure Drink collagene','30 stick','face-d-integratore-pure-drink',55.00),
  ('8057741883579','FD600F63050','Crema acido ialuronico Pure Plump 50 ml',null,'face-d-crema-viso-pure-plump-ha4-acido-ialuronico',34.00),
  ('8057741881636','FD600F33050','Crema liposomi di retinolo 50 ml',null,'crema-liposomi-di-retinolo',45.00)
on conflict (ean) do update
  set sku = excluded.sku, name = excluded.name, variant = excluded.variant,
      handle = excluded.handle, rrp = excluded.rrp, updated_at = now();

-- Amazon stesso come venditore autorizzato su Amazon.it
insert into public.sellers (site_id, seller_id, name, authorized)
select id, 'A11IL2PNWYJU7H', 'Amazon', true from public.sites where code = 'amazon'
on conflict (site_id, seller_id) do nothing;

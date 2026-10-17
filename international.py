"""CLDR locale/currency catalogs, user preferences and explicit display-only FX."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
import re
from zoneinfo import available_timezones
from babel import Locale, localedata
from babel.core import get_global
from babel.numbers import list_currencies, get_currency_name, get_currency_precision, format_currency
import advanced as a

PHRASES=['Business dashboard','Service marketplace','Marketplace orders','Purchased services','User manual','Support center & tickets','Language & currency','Customers','Vendors','Products','Invoices','Bills','Expenses','Employees','Tasks','Projects','Reports','Journals','Sign in','Sign out','Email','Password','Save','Back','Home','Refresh','Print','Search','Overview','Administration','Banking & tax','People & payroll','Automation','Platform','Business overview','Financial statements','Super admin','Provider provisioning & keys']
SEEDS={
 'es':['Panel empresarial','Mercado de servicios','Pedidos del mercado','Servicios adquiridos','Manual de usuario','Centro de soporte y tickets','Idioma y moneda','Clientes','Proveedores','Productos','Facturas','Facturas recibidas','Gastos','Empleados','Tareas','Proyectos','Informes','Asientos contables','Iniciar sesión','Cerrar sesión','Correo electrónico','Contraseña','Guardar','Atrás','Inicio','Actualizar','Imprimir','Buscar','Resumen','Administración','Banca e impuestos','Personal y nómina','Automatización','Plataforma','Resumen empresarial','Estados financieros','Superadministrador','Configuración de proveedores y claves'],
 'fr':['Tableau de bord','Marché de services','Commandes','Services achetés','Manuel utilisateur','Assistance et tickets','Langue et devise','Clients','Fournisseurs','Produits','Factures clients','Factures fournisseurs','Dépenses','Employés','Tâches','Projets','Rapports','Écritures','Connexion','Déconnexion','E-mail','Mot de passe','Enregistrer','Retour','Accueil','Actualiser','Imprimer','Rechercher','Vue générale','Administration','Banque et fiscalité','Personnel et paie','Automatisation','Plateforme','Vue de l’entreprise','États financiers','Super administrateur','Configuration des fournisseurs et clés'],
 'ar':['لوحة الأعمال','سوق الخدمات','طلبات السوق','الخدمات المشتراة','دليل المستخدم','الدعم والتذاكر','اللغة والعملة','العملاء','الموردون','المنتجات','الفواتير','فواتير الموردين','المصروفات','الموظفون','المهام','المشاريع','التقارير','القيود اليومية','تسجيل الدخول','تسجيل الخروج','البريد الإلكتروني','كلمة المرور','حفظ','رجوع','الرئيسية','تحديث','طباعة','بحث','نظرة عامة','الإدارة','البنوك والضرائب','الموظفون والرواتب','الأتمتة','المنصة','نظرة عامة على الأعمال','القوائم المالية','المسؤول العام','إعداد المزودين والمفاتيح'],
 'pt':['Painel empresarial','Mercado de serviços','Pedidos','Serviços adquiridos','Manual do usuário','Suporte e chamados','Idioma e moeda','Clientes','Fornecedores','Produtos','Faturas','Contas a pagar','Despesas','Funcionários','Tarefas','Projetos','Relatórios','Lançamentos','Entrar','Sair','E-mail','Senha','Salvar','Voltar','Início','Atualizar','Imprimir','Pesquisar','Visão geral','Administração','Bancos e impostos','Pessoal e folha','Automação','Plataforma','Visão empresarial','Demonstrações financeiras','Superadministrador','Provedores e chaves'],
 'de':['Geschäftsübersicht','Dienstleistungsmarkt','Bestellungen','Gekaufte Dienste','Benutzerhandbuch','Support und Tickets','Sprache und Währung','Kunden','Lieferanten','Produkte','Rechnungen','Lieferantenrechnungen','Ausgaben','Mitarbeiter','Aufgaben','Projekte','Berichte','Buchungen','Anmelden','Abmelden','E-Mail','Passwort','Speichern','Zurück','Start','Aktualisieren','Drucken','Suchen','Übersicht','Verwaltung','Banken und Steuern','Personal und Gehalt','Automatisierung','Plattform','Geschäftsübersicht','Finanzberichte','Superadministrator','Anbieter und Schlüssel'],
 'zh':['业务仪表板','服务市场','市场订单','已购服务','用户手册','支持与工单','语言与货币','客户','供应商','产品','发票','账单','费用','员工','任务','项目','报告','日记账','登录','退出','电子邮件','密码','保存','返回','主页','刷新','打印','搜索','概览','管理','银行与税务','人事与薪资','自动化','平台','业务概览','财务报表','超级管理员','服务商配置与密钥'],
 'hi':['व्यवसाय डैशबोर्ड','सेवा बाज़ार','बाज़ार ऑर्डर','खरीदी गई सेवाएँ','उपयोगकर्ता पुस्तिका','सहायता और टिकट','भाषा और मुद्रा','ग्राहक','विक्रेता','उत्पाद','चालान','बिल','खर्च','कर्मचारी','कार्य','परियोजनाएँ','रिपोर्ट','जर्नल','साइन इन','साइन आउट','ईमेल','पासवर्ड','सहेजें','वापस','होम','रीफ़्रेश','प्रिंट','खोजें','अवलोकन','प्रशासन','बैंकिंग और कर','कार्मिक और वेतन','स्वचालन','प्लेटफ़ॉर्म','व्यवसाय अवलोकन','वित्तीय विवरण','सुपर एडमिन','प्रदाता और कुंजियाँ'],
 'yo':['Àkótán iṣẹ́','Ọjà iṣẹ́','Àwọn àṣẹ ọjà','Àwọn iṣẹ́ tí a rà','Ìwé ìtọ́sọ́nà','Ìrànlọ́wọ́ àti tikẹ́ẹ̀tì','Èdè àti owó','Àwọn oníbàárà','Àwọn olùpèsè','Àwọn ọjà','Ìwé owó','Owó tí a gbọ́dọ̀ san','Ìnáwó','Àwọn òṣìṣẹ́','Àwọn iṣẹ́','Àwọn iṣẹ́ àkànṣe','Ìròyìn','Àkọsílẹ̀ owó','Wọlé','Jáde','Ímeèlì','Ọ̀rọ̀ aṣínà','Fipamọ́','Padà','Ilé','Túnṣe','Tẹ̀ jáde','Wá','Àkótán','Ìṣàkóso','Ilé ìfowópamọ́ àti owó orí','Òṣìṣẹ́ àti owó oṣù','Ìṣiṣẹ́ aládàáṣiṣẹ́','Pẹpẹ','Àkótán iṣẹ́','Ìròyìn owó','Olùṣàkóso àgbà','Ìṣètò olùpèsè àti kọ́kọ́rọ́'],
 'ha':['Allon kasuwanci','Kasuwar ayyuka','Odar kasuwa','Ayyukan da aka saya','Jagorar mai amfani','Tallafi da tikiti','Harshe da kuɗi','Abokan ciniki','Masu kaya','Kayayyaki','Rasitan biyan kuɗi','Kuɗin da za a biya','Kashe kuɗi','Ma’aikata','Ayyuka','Shirye-shirye','Rahotanni','Kundin lissafi','Shiga','Fita','Imel','Kalmar sirri','Ajiye','Baya','Gida','Sabunta','Buga','Nema','Bayani','Gudanarwa','Banki da haraji','Ma’aikata da albashi','Aiki na atomatik','Dandali','Bayanin kasuwanci','Rahotannin kuɗi','Babban mai gudanarwa','Saitin masu samarwa da maɓallai'],
 'ig':['Nchịkọta azụmahịa','Ahịa ọrụ','Iwu ahịa','Ọrụ a zụtara','Ntuziaka onye ọrụ','Nkwado na tiketi','Asụsụ na ego','Ndị ahịa','Ndị na-eweta ihe','Ngwaahịa','Akwụkwọ ụgwọ','Ụgwọ a ga-akwụ','Mmefu','Ndị ọrụ','Ọrụ','Atụmatụ','Akụkọ','Ndekọ ego','Banye','Pụọ','Ozi ịntanetị','Okwuntughe','Chekwaa','Laghachi','Ụlọ','Melite','Bipụta','Chọọ','Nchịkọta','Nlekọta','Ụlọ akụ na ụtụ isi','Ndị ọrụ na ụgwọ ọnwa','Ọrụ akpaka','Ikpo okwu','Nchịkọta azụmahịa','Akụkọ ego','Onye nchịkwa ukwu','Ntọala ndị na-eweta ọrụ na igodo'],
 'sw':['Dashibodi ya biashara','Soko la huduma','Maagizo ya soko','Huduma zilizonunuliwa','Mwongozo wa mtumiaji','Msaada na tiketi','Lugha na sarafu','Wateja','Wasambazaji','Bidhaa','Ankara','Bili','Matumizi','Wafanyakazi','Kazi','Miradi','Ripoti','Majarida ya uhasibu','Ingia','Toka','Barua pepe','Nenosiri','Hifadhi','Rudi','Nyumbani','Onyesha upya','Chapisha','Tafuta','Muhtasari','Utawala','Benki na kodi','Wafanyakazi na mishahara','Otomatiki','Jukwaa','Muhtasari wa biashara','Taarifa za fedha','Msimamizi mkuu','Mipangilio ya watoa huduma na funguo']}

@lru_cache(maxsize=1)
def catalogs():
 locales=[]
 for identifier in localedata.locale_identifiers():
  if identifier=='root' or '@' in identifier:continue
  loc=Locale.parse(identifier);code=identifier.replace('_','-')
  locales.append({'id':code,'name':loc.get_display_name('en') or code,'native':loc.get_display_name(loc) or loc.get_display_name('en') or code,'direction':'rtl' if loc.character_order=='right-to-left' else 'ltr'})
 active=set();today=date.today()
 for entries in get_global('territory_currencies').values():
  for code,start,end,tender in entries:
   if tender and (not start or date(*start)<=today) and (not end or date(*end)>=today):active.add(code)
 currencies=[{'id':code,'name':get_currency_name(code,locale='en'),'digits':get_currency_precision(code),'active':code in active} for code in sorted(list_currencies()) if code not in ('XXX','XTS')]
 return {'locales':sorted(locales,key=lambda x:x['name']),'currencies':currencies,'timezones':sorted(available_timezones()),'translation_seed_languages':['en']+list(SEEDS),'ledger_currency':'USD','notice':'Locale coverage is broader than translated interface coverage. Missing translations use English. Currency preferences never relabel existing USD ledger entries.'}

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS user_preferences(user_id INTEGER PRIMARY KEY,locale TEXT NOT NULL,currency TEXT NOT NULL,timezone TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS ui_translations(locale TEXT NOT NULL,phrase TEXT NOT NULL,translation TEXT NOT NULL,PRIMARY KEY(locale,phrase));
 CREATE TABLE IF NOT EXISTS display_fx(currency TEXT PRIMARY KEY,per_usd TEXT NOT NULL,as_of TEXT NOT NULL,source TEXT NOT NULL);''')

def preferences(c,uid):
 row=c.execute('SELECT locale,currency,timezone FROM user_preferences WHERE user_id=?',(uid,)).fetchone()
 return dict(row) if row else {'locale':'en-US','currency':'USD','timezone':'UTC'}

def bundle(c,locale):
 base=locale.split('-')[0];result=dict(zip(PHRASES,SEEDS.get(base,[])))
 result.update({r['phrase']:r['translation'] for r in c.execute('SELECT phrase,translation FROM ui_translations WHERE locale=?',(base,))})
 result.update({r['phrase']:r['translation'] for r in c.execute('SELECT phrase,translation FROM ui_translations WHERE locale=?',(locale,))})
 return result

def convert(c,minor,currency):
 value=Decimal(minor)/100
 if currency=='USD':return {'amount':str(value),'currency':'USD','converted':False}
 row=c.execute('SELECT * FROM display_fx WHERE currency=?',(currency,)).fetchone()
 if not row:return {'amount':str(value),'currency':'USD','converted':False,'notice':'No reference rate configured for '+currency}
 age=(date.today()-date.fromisoformat(row['as_of'])).days
 if age>7:return {'amount':str(value),'currency':'USD','converted':False,'notice':'Reference rate is stale; showing USD'}
 return {'amount':str(value*Decimal(row['per_usd'])),'currency':currency,'converted':True,'as_of':row['as_of'],'source':row['source'],'notice':'Display estimate only; not a transaction or settlement rate'}

def dispatch(path,method,body,c,user):
 if not path.startswith('/api/intl/'):return None
 route=path[len('/api/intl/'):];catalog=catalogs();locales={x['id'] for x in catalog['locales']};currencies={x['id'] for x in catalog['currencies']};pref=preferences(c,user['id'])
 if route=='preferences':
  if method=='POST':
   if body.get('locale') not in locales or body.get('currency') not in currencies or body.get('timezone') not in catalog['timezones']:raise a.ServiceError('Select a known locale, currency and time zone')
   c.execute('INSERT OR REPLACE INTO user_preferences VALUES(?,?,?,?)',(user['id'],body['locale'],body['currency'],body['timezone']));pref=preferences(c,user['id'])
  return pref
 if route=='bundle' and method=='GET':return {'preferences':pref,'translations':bundle(c,pref['locale']),'rates':[dict(r) for r in c.execute('SELECT * FROM display_fx')],'phrases':PHRASES}
 if route=='format' and method=='POST':
  code=body.get('currency',pref['currency']);locale=body.get('locale',pref['locale'])
  if code not in currencies or locale not in locales:raise a.ServiceError('Unknown currency or locale')
  try:value=Decimal(str(body.get('amount','0')))
  except InvalidOperation:raise a.ServiceError('Invalid amount') from None
  if not value.is_finite() or abs(value)>Decimal('1000000000000'):raise a.ServiceError('Invalid amount')
  return {'formatted':format_currency(value,code,locale=locale.replace('-','_')),'currency':code,'digits':get_currency_precision(code)}
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if route=='translations':
  locale=body.get('locale',pref['locale'])
  if locale not in locales:raise a.ServiceError('Unknown locale')
  if method=='POST':
   entries=body.get('entries')
   if not isinstance(entries,dict) or len(entries)>500:raise a.ServiceError('Supply up to 500 translation entries')
   for phrase,value in entries.items():
    if not isinstance(value,str) or not 0<len(phrase)<=2000 or len(value)>4000 or re.search('[<>]',phrase+value):raise a.ServiceError('Use plain-text translation entries without HTML')
   for phrase,value in entries.items():
    if value:c.execute('INSERT OR REPLACE INTO ui_translations VALUES(?,?,?)',(locale,phrase,value))
    else:c.execute('DELETE FROM ui_translations WHERE locale=? AND phrase=?',(locale,phrase))
   a.audit(c,user['id'],'Translations updated '+locale)
  return bundle(c,locale)
 if route=='rates':
  if method=='POST':
   currency=body.get('currency');source=str(body.get('source','')).strip()
   if currency not in currencies or currency=='USD' or not 1<=len(source)<=200:raise a.ServiceError('Select a non-USD currency and identify the rate source')
   try:rate=Decimal(str(body.get('per_usd')));as_of=date.fromisoformat(body.get('as_of',''))
   except (InvalidOperation,ValueError):raise a.ServiceError('Supply a valid rate and ISO date') from None
   if not rate.is_finite() or not Decimal('0')<rate<=Decimal('1000000000000') or as_of>date.today():raise a.ServiceError('Rate must be positive and its date cannot be in the future')
   c.execute('INSERT OR REPLACE INTO display_fx VALUES(?,?,?,?)',(currency,str(rate),as_of.isoformat(),source));a.audit(c,user['id'],'Display reference rate updated '+currency)
  return [dict(r) for r in c.execute('SELECT * FROM display_fx')]
 raise a.ServiceError('Internationalization route not found',404)

"""Versioned IRS-source ordinary-income projections, not a complete tax/filing engine."""
from decimal import Decimal, ROUND_HALF_UP
import advanced as a
RULES={
 2021:{'standard':12550,'brackets':[9950,40525,86375,164925,209425,523600]},
 2022:{'standard':12950,'brackets':[10275,41775,89075,170050,215950,539900]},
 2023:{'standard':13850,'brackets':[11000,44725,95375,182100,231250,578125]},
 2024:{'standard':14600,'brackets':[11600,47150,100525,191950,243725,609350]},
 2025:{'standard':15750,'brackets':[11925,48475,103350,197300,250525,626350]},
 2026:{'standard':16100,'brackets':[12400,50400,105700,201775,256225,640600]},
}

def sources(year):
 return [{'title':str(year)+' IRS estimated-tax rate schedules','url':'https://www.irs.gov/pub/irs-prior/f1040es--'+str(year)+'.pdf'},
 {'title':str(year)+' IRS return instructions (use latest revision)','url':'https://www.irs.gov/pub/irs-prior/i1040gi--'+str(year)+'.pdf'}] if year!=2026 else [{'title':'IRS 2026 inflation adjustments','url':'https://www.irs.gov/pub/irs-drop/rp-25-32.pdf'},{'title':'IRS 2026 projected tax guidance','url':'https://www.irs.gov/publications/p505'}]

def estimate(year,income):
 if year not in RULES:raise a.ServiceError('Year-specific calculation rules are unavailable',503)
 rule=RULES[year];gross=a.cents(income);taxable=max(0,gross-rule['standard']*100);tax=Decimal(0);lower=0
 for upper,rate in zip([b*100 for b in rule['brackets']]+[None],['0.10','0.12','0.22','0.24','0.32','0.35','0.37']):
  portion=max(0,min(taxable,upper) - lower) if upper is not None else max(0,taxable-lower)
  tax+=Decimal(portion)*Decimal(rate)
  if upper is None or taxable<=upper:break
  lower=upper
 return {'year':year,'filing_status':'single','standard_deduction_cents':rule['standard']*100,'taxable_income_cents':taxable,'ordinary_income_tax_cents':int(tax.quantize(Decimal('1'),rounding=ROUND_HALF_UP)),'estimate_only':True,'source':sources(year),'scope':'Single-filer ordinary-income projection only. Not a final return tax-table calculation, complete liability or refund guarantee.'}

# Copyright (c) 2023, Elite Resources and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import json

class PayrollInvoicesGenerator(Document):
	pass

@frappe.whitelist()
def get_employees(project,start_date,end_date,month_name):
	employees = frappe.get_all('Employee', filters={'status': 'Active', 'project':project}, fields=['name','employee_name'])

	filtered_employees = []
	if project == "PROJ-0007" or project == "PROJ-0004": #if project equal to Alhokair or Nomac NMES
		for employee in employees:
			if not frappe.db.exists("Payroll Processed",{"employee": employee["name"],"month_name":month_name,"project": project}):
				filtered_employees.append(employee)
	else:
		for employee in employees:
			salary_slip = frappe.get_value(
				"Salary Slip",
				filters={"employee": employee["name"], "invoice_created": 0,"start_date": start_date, "end_date": end_date, "docstatus": 1},
				fieldname="name",
			)
			if salary_slip:
				employee["salary_slip"] = salary_slip
				filtered_employees.append(employee)
		if not filtered_employees:
			frappe.throw(_("No Salary slip exists in the period from {0} to {1}".format(start_date,end_date)))
	
	return filtered_employees

@frappe.whitelist()
def get_allow_po_mgt_employees(project,start_date,end_date,type=None):
	if project == "PROJ-0001": #when project misk because employment type use in misk
		employees = frappe.get_all('Employee', filters={'status': 'Active', 'project':project,'employment_type': type}, fields=['name','employee_name'])
	else:
		employees = frappe.get_all('Employee', filters={'status': 'Active', 'project':project}, fields=['name','employee_name'])

	filtered_employees = []
	for employee in employees:
		salary_slip = frappe.get_value(
			"Salary Slip",
			filters={"employee": employee["name"], "invoice_created": 0,"start_date": start_date, "end_date": end_date, "docstatus": 1},
			fieldname="name",
		)
		if salary_slip:
			employee["salary_slip"] = salary_slip
			filtered_employees.append(employee)

	for emp in filtered_employees:
		po_mgt_list = frappe.db.get_list('PO Management',
							filters={
								'status': 'Active',
								'docstatus': 1,
								'employee_no': emp["name"],
								'project_no': 'PROJ-0001'
							},
							fields=['name'],
							order_by='creation asc'
						)
		rem_units = 0
		for po_mgt in po_mgt_list:
			po_mdoc = frappe.get_doc("PO Management", po_mgt.name)
			rem_units = rem_units + po_mdoc.remaining_units
		
		if rem_units > 0:
			emp["remaining_units"] = rem_units
	if not filtered_employees:
		frappe.throw(_("No Salary slip exists in the period from {0} to {1}".format(start_date,end_date)))

	return filtered_employees


@frappe.whitelist()
def generate_invoices(project,due_date,customer,invoice_type,employees,month_name,my_in_arabic,year):
	emps = json.loads(employees)
	if invoice_type == "One Invoice with all employees details":
		si = create_si_without_item(customer,due_date,project)

		for emp in emps:
			mp_cost = manpower_cost_calculation(emp["employee"],emp["salary_slip"])
			si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=emp["employee"],mp_qty=1,mp_cost=mp_cost)
			si.append("items", si_item)

			gosi_cost = gosi_cost_calculation(emp["employee"])
			si_item = create_gosi_item(month_name,year,emp_id=emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
			si.append("items", si_item)

		si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=len(emps))
		si.append("items", si_item)

		si_item = create_bank_charges_item(project,month_name,year,bt_qty=len(emps))
		si.append("items", si_item)
		
		si_tax = create_vat_tax()
		si.append("taxes", si_tax)

		si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
		si.remarks = "Payroll Invoice"
		si.save(ignore_permissions=True)

		if si.name:
			for emp in emps:
				update_salary_slip(emp)
			status = True

	elif invoice_type == "One Invoice with all employees details sumup each emp in one line":
		si = create_si_without_item(customer,due_date,project)

		for emp in emps:
			total_mp = 0
			total_mp = manpower_cost_calculation(emp["employee"],emp["salary_slip"]) + gosi_cost_calculation(emp["employee"]) + frappe.db.get_value("Project", {"name":project}, "erc_fee")

			si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=emp["employee"],mp_qty=1,mp_cost=total_mp)
			si.append("items", si_item)
		
		si_item = create_bank_charges_item(project,month_name,year,bt_qty=len(emps))
		si.append("items", si_item)

		si_tax = create_vat_tax()
		si.append("taxes", si_tax)

		si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
		si.remarks = "Payroll Invoice"
		si.save(ignore_permissions=True)

		if si.name:
			for emp in emps:
				update_salary_slip(emp)
			status = True

	elif invoice_type == "One Invoice with all employees total one line only":
		si = create_si_without_item(customer,due_date,project)
		project_doc = frappe.get_doc("Project",project)
		total_mp = 0

		for emp in emps:
			total_mp = total_mp + manpower_cost_calculation(emp["employee"],emp["salary_slip"]) + gosi_cost_calculation(emp["employee"]) + project_doc.erc_fee + project_doc.bt_charges
		
		si_item = create_manpower_item(month_name,year,my_in_arabic,mp_qty=1,mp_cost=total_mp)
		si.append("items", si_item)

		si_tax = create_vat_tax()
		si.append("taxes", si_tax)

		si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
		si.remarks = "Payroll Invoice"
		si.save(ignore_permissions=True)

		if si.name:
			for emp in emps:
				update_salary_slip(emp)
			status = True
	
	elif invoice_type == "One Invoice with all employees total one line only without gosi and btc":
		si = create_si_without_item(customer,due_date,project)
		total_mp = 0

		for emp in emps:
			housing_adv_loan = 0
			sslp_doc = frappe.get_doc("Salary Slip",emp["salary_slip"])
			if sslp_doc.loans:
				for loan in sslp_doc.loans:
					if loan.loan_type == "Housing Advance":
						housing_adv_loan = housing_adv_loan + loan.total_payment

			total_mp = total_mp + sslp_doc.net_pay + sslp_doc.total_loan_repayment - housing_adv_loan + frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_elite_monthly_fee")

		si_item = create_manpower_item(month_name,year,my_in_arabic,mp_qty=1,mp_cost=total_mp)
		si.append("items", si_item)

		si_tax = create_vat_tax()
		si.append("taxes", si_tax)

		si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
		si.remarks = "Payroll Invoice"
		si.save(ignore_permissions=True)

		if si.name:
			for emp in emps:
				update_salary_slip(emp)
			status = True	

	elif invoice_type == "Invoice based on per PO":
		#frappe.errprint(emps)
		po_list = []
		for emp in emps:
			po_no = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no")
			if po_no not in po_list:
				po_list.append(po_no)
		for po in po_list:
			si = create_si_without_item(customer,due_date,project)
			si.po_no = po
			qty = 0
			for emp in emps:
				si.print_customer = frappe.db.get_value("Employee", {"name":emp["employee"]}, "print_customer_for_invoice")
				if po == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no"):
					qty += 1
					mp_cost = manpower_cost_calculation(emp["employee"],emp["salary_slip"])
					si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=emp["employee"],mp_qty=1,mp_cost=mp_cost)
					si.append("items", si_item)

					gosi_cost = gosi_cost_calculation(emp["employee"])
					si_item = create_gosi_item(month_name,year,emp_id=emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
					si.append("items", si_item)
			
			si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=qty)
			si.append("items", si_item)

			si_item = create_bank_charges_item(project,month_name,year,bt_qty=qty)
			si.append("items", si_item)

			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			si.save(ignore_permissions=True)

			if si.name:
				for emp in emps:
					if po == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no"):
						update_salary_slip(emp)
				status = True

	elif invoice_type == "Invoice based on per Employee":
		for emp in emps:
			si = create_si_without_item(customer,due_date,project)

			mp_cost = manpower_cost_calculation(emp["employee"],emp["salary_slip"])
			si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=emp["employee"],mp_qty=1,mp_cost=mp_cost)
			si.append("items", si_item)

			gosi_cost = gosi_cost_calculation(emp["employee"])
			si_item = create_gosi_item(month_name,year,emp_id=emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
			si.append("items", si_item)

			si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=1)
			si.append("items", si_item)

			si_item = create_bank_charges_item(project,month_name,year,bt_qty=1)
			si.append("items", si_item)
			
			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			si.save(ignore_permissions=True)

			if si.name:
				update_salary_slip(emp)
				status = True

	elif invoice_type == "Invoice based on per PO with other POs":
		po_list = []
		po_for_rota_list = []
		po_for_neom_list = []
		for emp in emps:
			po_no = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no")
			if po_no not in po_list:
				po_list.append(po_no)

			po_for_re = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_rotation_expense")
			if po_for_re == 1:
				po_no_for_re = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no_for_rotation")
				if po_no_for_re not in po_for_rota_list:
					po_for_rota_list.append(po_no_for_re)

			po_for_na = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_neom_allowance")
			if po_for_na == 1:
				po_no_for_na = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no_for_neom")
				if po_no_for_na not in po_for_neom_list:
					po_for_neom_list.append(po_no_for_na)		

		#frappe.errprint(po_list)
		#frappe.errprint(po_for_rota_list)
		#frappe.errprint(po_for_neom_list)

		for po_rota in po_for_rota_list:
			si = create_si_without_item(customer,due_date,project)
			si.po_no = po_rota
			for emp in emps:
				if po_rota == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no_for_rotation"):
					po_for_re = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_rotation_expense")
					sc_for_rotation = frappe.db.get_value("Employee", {"name":emp["employee"]}, "s_c_for_rotation")
					if po_for_re == 1 and frappe.db.exists("Salary Detail",{"parent": emp["salary_slip"],"salary_component": sc_for_rotation}):
						si_item = frappe.new_doc("Sales Invoice Item")
						si_item.item_code = 912
						si_item.qty = 1
						si_item.rate = float(frappe.db.get_value("Salary Detail", {"parent":emp["salary_slip"], "salary_component": sc_for_rotation}, "amount"))
						si_item.employee_id = emp["employee"]
						si_item.employee_name = emp["employee_name"]
						if si_item.rate > 0.0:
							si.append("items", si_item)

						si_item = frappe.new_doc("Sales Invoice Item")
						si_item.item_code = 915
						si_item.qty = 1
						si_item.rate = float(frappe.db.get_value("Salary Detail", {"parent":emp["salary_slip"], "salary_component": sc_for_rotation}, "amount")) * 0.1
						si_item.employee_id = emp["employee"]
						si_item.employee_name = emp["employee_name"]
						if si_item.rate > 0.0:
							si.append("items", si_item)

			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			#if items exist then invoice save in the system otherwise skip it.
			if len(si.items) > 0:
				si.save(ignore_permissions=True)

		for po_neom in po_for_neom_list:
			si = create_si_without_item(customer,due_date,project)
			si.po_no = po_neom
			for emp in emps:
				if po_neom == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no_for_neom"):
					po_for_na = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_neom_allowance")
					sc_for_neom = frappe.db.get_value("Employee", {"name":emp["employee"]}, "s_c_for_neom")
					if po_for_na == 1 and frappe.db.exists("Salary Detail",{"parent": emp["salary_slip"],"salary_component": sc_for_neom}):
						si_item = frappe.new_doc("Sales Invoice Item")
						si_item.item_code = 916
						si_item.qty = 1
						si_item.rate = frappe.db.get_value("Salary Detail", {"parent":emp["salary_slip"], "salary_component": sc_for_neom}, "amount")
						si_item.employee_id = emp["employee"]
						si_item.employee_name = emp["employee_name"]
						if si_item.rate > 0.0:
							si.append("items", si_item)

			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			#if items exist then invoice save in the system otherwise skip it.
			if len(si.items) > 0:
				si.save(ignore_permissions=True)
		
		for po in po_list:
			si = create_si_without_item(customer,due_date,project)
			si.po_no = po
			qty = 0
			for emp in emps:
				if po == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no"):
					qty += 1
					manpower = 0

					manpower = manpower + manpower_cost_calculation(emp["employee"],emp["salary_slip"])

					po_for_re = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_rotation_expense")
					sc_for_rotation = ""
					if po_for_re == 1:
						sc_for_rotation = frappe.db.get_value("Employee", {"name":emp["employee"]}, "s_c_for_rotation")
						re_amount = frappe.db.get_value("Salary Detail", {"parent":emp["salary_slip"], "salary_component": sc_for_rotation}, "amount")
						if re_amount:
							manpower = manpower - re_amount

					po_for_na = frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_for_neom_allowance")
					sc_for_neom = ""
					if po_for_na == 1:
						sc_for_neom = frappe.db.get_value("Employee", {"name":emp["employee"]}, "s_c_for_neom")
						na_amount = frappe.db.get_value("Salary Detail", {"parent":emp["salary_slip"], "salary_component": sc_for_neom}, "amount")
						if na_amount:
							manpower = manpower - na_amount

					si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=emp["employee"],mp_qty=1,mp_cost=manpower)
					si.append("items", si_item)

					gosi_cost = gosi_cost_calculation(emp["employee"])
					si_item = create_gosi_item(month_name,year,emp_id=emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
					si.append("items", si_item)

			si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=qty)
			si.append("items", si_item)

			si_item = create_bank_charges_item(project,month_name,year,bt_qty=qty)
			si.append("items", si_item)

			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			si.save(ignore_permissions=True)

			if si.name:
				for emp in emps:
					if po == frappe.db.get_value("Employee", {"name":emp["employee"]}, "po_no"):
						update_salary_slip(emp)
				status = True

	elif invoice_type == "One Invoice with all employees total dept under loc wise one line only":
		dept_list = []
		loc_list = []
		for emp in emps:
			dept = frappe.db.get_value("Employee", {"name":emp["employee"]}, "department")
			loc = frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_location")
			if dept not in dept_list:
				dept_list.append(dept)

			if loc not in loc_list:
				loc_list.append(loc)	
		
		for dp in dept_list:
			for lc in loc_list:
				total_mp = 0
				for emp in emps:
					if dp == frappe.db.get_value("Employee", {"name":emp["employee"]}, "department") and lc == frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_location"):
						#manpower, gosi, erc fee, and bank transaction charges adding into total_mp
						project_doc = frappe.get_doc("Project",project)
						total_mp = total_mp + manpower_cost_calculation(emp["employee"],emp["salary_slip"]) + gosi_cost_calculation(emp["employee"]) + project_doc.erc_fee + project_doc.bt_charges
				if total_mp > 0:
					si = create_si_without_item(customer,due_date,project)

					si_item = create_manpower_item(month_name,year,my_in_arabic,mp_qty=1,mp_cost=total_mp)
					si_item.item_name = f"{dp} - {lc}"
					si.append("items", si_item)

					si_tax = create_vat_tax()
					si.append("taxes", si_tax)

					si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
					si.remarks = "Payroll Invoice"
					si.save(ignore_permissions=True)

					if si.name:
						for emp in emps:
							if dp == frappe.db.get_value("Employee", {"name":emp["employee"]}, "department") and lc == frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_location"):
								update_salary_slip(emp)
						status = True

	elif invoice_type == "One Invoice with dept wise all employees total one line only":
		dept_list = []
		for emp in emps:
			dept = frappe.db.get_value("Employee", {"name":emp["employee"]}, "department")
			if dept not in dept_list:
				dept_list.append(dept)
		
		for dp in dept_list:
			total_mp = 0
			for emp in emps:
				if dp == frappe.db.get_value("Employee", {"name":emp["employee"]}, "department"):
					#manpower, gosi, erc fee, and bank transaction charges adding into total_mp
					project_doc = frappe.get_doc("Project",project)
					total_mp = total_mp + manpower_cost_calculation(emp["employee"],emp["salary_slip"]) + gosi_cost_calculation(emp["employee"]) + project_doc.erc_fee + project_doc.bt_charges
			if total_mp > 0:
				si = create_si_without_item(customer,due_date,project)

				si_item = create_manpower_item(month_name,year,my_in_arabic,mp_qty=1,mp_cost=total_mp)
				si.append("items", si_item)

				si_tax = create_vat_tax()
				si.append("taxes", si_tax)

				si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
				si.remarks = "Payroll Invoice"
				si.save(ignore_permissions=True)

				if si.name:
					for emp in emps:
						if dp == frappe.db.get_value("Employee", {"name":emp["employee"]}, "department"):
							update_salary_slip(emp)
					status = True					
	
	elif invoice_type == "Division(dept) wise invoices Alhokair":
		dept_list = []
		for emp in emps:
			dept = frappe.db.get_value("Employee", {"name":emp["employee"]}, "department")
			if dept and dept not in dept_list:
				dept_list.append(dept)

		for dept in dept_list:
			no_emps_of_dept = 0
			slted_emps = []
			for emp in emps:
				if dept == frappe.db.get_value("Employee", {"name":emp["employee"]}, "department"):
					no_emps_of_dept += 1
					slted_emps.append(emp["employee"])
		
			if dept != "Holding Bus Tour":
				if no_emps_of_dept > 0 and slted_emps:
					si = create_si_without_item(customer,due_date,project)

					mp_cost = frappe.db.get_value("Department", {"name":dept}, "custom_month_erc_cost")
					si_item = create_manpower_item(month_name,year,my_in_arabic,mp_qty=no_emps_of_dept,mp_cost=mp_cost)
					si_item.item_name = f"{dept} - Operational Cost of employees"
					si.append("items", si_item)

					si_tax = create_vat_tax()
					si.append("taxes", si_tax)

					si.remarks = "Payroll Invoice"
					si.save(ignore_permissions=True)

					if si.name:
						for s_emp in slted_emps:
							create_payroll_processed(s_emp,month_name,project)
			elif dept == "Holding Bus Tour":
				if no_emps_of_dept > 0 and slted_emps:
					si = create_si_without_item(customer,due_date,project)

					for s_emp in slted_emps:
						mp_cost = frappe.db.get_value("Department", {"name":dept}, "custom_month_erc_cost")
						si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=s_emp,mp_qty=1,mp_cost=mp_cost)
						si_item.item_name = f"{dept} - Operational Cost of employees"
						si.append("items", si_item)
						
						gosi_cost = gosi_cost_calculation(s_emp)
						si_item = create_gosi_item(month_name,year,emp_id=s_emp,gosi_qty=1,gosi_cost=gosi_cost)
						si.append("items", si_item)
						
						si_item = frappe.new_doc("Sales Invoice Item")
						si_item.item_code = 632
						si_item.employee_id = s_emp
						si_item.qty = 1
						si_item.rate = 125
						si.append("items", si_item)

					si_tax = create_vat_tax()
					si.append("taxes", si_tax)

					si.remarks = "Payroll Invoice"
					si.save(ignore_permissions=True)

					if si.name:
						for s_emp in slted_emps:
							create_payroll_processed(s_emp,month_name,project)

		status = True
	
	elif invoice_type == "Location wise Invoices with all employees details separately":
		loc_list = []
		for emp in emps:
			location = frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_location")
			if location and location not in loc_list:
				loc_list.append(location)

		for lc in loc_list:
			no_emps_of_loc = 0
			slted_emps = [] #selected employee of location (lc)
			for emp in emps:
				if lc == frappe.db.get_value("Employee", {"name":emp["employee"]}, "custom_location"):
					no_emps_of_loc += 1
					slted_emps.append(emp)
		
			#frappe.errprint(lc)
			#frappe.errprint(no_emps_of_loc)
			#frappe.errprint(slted_emps)
			if no_emps_of_loc > 0 and slted_emps:
				si = create_si_without_item(customer,due_date,project)
				si.custom_location = lc

				for s_emp in slted_emps:
					mp_cost = manpower_cost_calculation(emp["employee"],emp["salary_slip"])
					si_item = create_manpower_item(month_name,year,my_in_arabic,emp_id=s_emp["employee"],mp_qty=1,mp_cost=mp_cost)
					si.append("items", si_item)

					gosi_cost = gosi_cost_calculation(s_emp["employee"])
					si_item = create_gosi_item(month_name,year,emp_id=s_emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
					si.append("items", si_item)

				si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=no_emps_of_loc)
				si.append("items", si_item)

				si_item = create_bank_charges_item(project,month_name,year,bt_qty=no_emps_of_loc)
				si.append("items", si_item)

				si_tax = create_vat_tax()
				si.append("taxes", si_tax)

				si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
				si.remarks = "Payroll Invoice"
				si.save(ignore_permissions=True)

				if si.name:
					for emp in slted_emps:
						update_salary_slip(emp)
		
		status = True

	elif invoice_type == "Employee Wise Invoices with PO from PO Mgt":
		for emp in emps:
			po_mgt_list = frappe.db.get_list('PO Management',
							filters={
								'status': 'Active',
								'docstatus': 1,
								'employee_no': emp["employee"],
								'project_no': project,
								'po_type': 'Manpower'
							},
							fields=['name'],
							order_by='creation asc'
						)

			r_wd = emp["working_days"]
			for po_mgt in po_mgt_list:
				po_mdoc = frappe.get_doc("PO Management", po_mgt.name)
				invoicing_rate = po_mdoc.invoicing_rate
				used_units = po_mdoc.used_units
				remaining_units = po_mdoc.remaining_units

				if remaining_units >= r_wd and r_wd != 0:
					#rate = r_wd * invoicing_rate
					diff_units = remaining_units - r_wd
					used_units = used_units + r_wd

					si = create_si_without_item(customer,due_date,project)
					si.print_customer = frappe.db.get_value("Employee", {"name":emp["employee"]}, "print_customer_for_invoice")
					si.po_no = po_mdoc.po_no

					#emp_working_days will use in the qty of item row
					emp_working_days = r_wd
					si_item = create_manpower_item_for_wdays(emp,month_name,year,my_in_arabic,emp_working_days,invoicing_rate)
					si.append("items", si_item)

					si_tax = create_vat_tax()
					si.append("taxes", si_tax)

					si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
					si.remarks = "Payroll Invoice"
					si.save(ignore_permissions=True)
					
					if si.name:
						update_salary_slip(emp)
					
					r_wd = 0
					po_mdoc.used_units = used_units
					po_mdoc.remaining_units = diff_units
					po_mdoc.save(ignore_permissions=True)
					if po_mdoc.remaining_units == 0:
						po_mdoc.status = "Completed"
						po_mdoc.save(ignore_permissions=True)
					status = True	

				elif r_wd > remaining_units:
					#rate = remaining_units * invoicing_rate
					r_wd = r_wd - remaining_units
					used_units = used_units + remaining_units

					si = create_si_without_item(customer,due_date,project)
					si.print_customer = frappe.db.get_value("Employee", {"name":emp["employee"]}, "print_customer_for_invoice")
					si.po_no = po_mdoc.po_no

					#emp_working_days will use in the qty of item row
					emp_working_days = remaining_units
					si_item = create_manpower_item_for_wdays(emp,month_name,year,my_in_arabic,emp_working_days,invoicing_rate)
					si.append("items", si_item)

					si_tax = create_vat_tax()
					si.append("taxes", si_tax)

					si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
					si.remarks = "Payroll Invoice"
					si.save(ignore_permissions=True)

					if si.name:
						update_salary_slip(emp)

					remaining_units = 0
					po_mdoc.used_units = used_units
					po_mdoc.remaining_units = remaining_units
					po_mdoc.save(ignore_permissions=True)
					if po_mdoc.remaining_units == 0:
						po_mdoc.status = "Completed"
						po_mdoc.save(ignore_permissions=True)
					status = True

	elif invoice_type == "Employee Wise Invoices without PO from PO Mgt":
		for emp in emps:
			po_mgt_list = frappe.db.get_list('PO Management',
							filters={
								'status': 'Active',
								'docstatus': 1,
								'employee_no': emp["employee"],
								'project_no': project,
								'po_type': 'Manpower'
							},
							pluck='name',
							order_by='creation asc'
						)
			
			po_mdoc = frappe.get_doc("PO Management", po_mgt_list[0])
			invoicing_rate = po_mdoc.invoicing_rate
			emp_working_days = emp["working_days"]
				
			si = create_si_without_item(customer,due_date,project)

			si_item = create_manpower_item_for_wdays(emp,month_name,year,my_in_arabic,emp_working_days,invoicing_rate)
			si.append("items", si_item)

			si_tax = create_vat_tax()
			si.append("taxes", si_tax)

			si.custom_payroll_entry_link = frappe.db.get_value("Salary Slip", emps[0]["salary_slip"], "payroll_entry")
			si.remarks = "Payroll Invoice"
			si.save(ignore_permissions=True)
					
			if si.name:
				update_salary_slip(emp)
					
				status = True

	elif invoice_type == "One Invoice with all employees gosi and erc fee without payroll":
		si = create_si_without_item(customer,due_date,project)

		for emp in emps:
			gosi_cost = gosi_cost_calculation(emp["employee"])
			si_item = create_gosi_item(month_name,year,emp_id=emp["employee"],gosi_qty=1,gosi_cost=gosi_cost)
			si.append("items", si_item)

		si_item = create_erc_fee_item(project,month_name,year,erc_fee_qty=len(emps))
		si.append("items", si_item)

		si_tax = create_vat_tax()
		si.append("taxes", si_tax)
		si.remarks = "Payroll Invoice"
		si.save(ignore_permissions=True)

		if si.name:
			for emp in emps:
				create_payroll_processed(emp["employee"],month_name,project)

		status = True

	return status

@frappe.whitelist()
def create_si_without_item(customer,due_date,project):
	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.set_posting_time = 1
	si.posting_date = due_date
	si.due_date = due_date
	si.project = project
	si.is_pos = 0

	return si

@frappe.whitelist()
def manpower_cost_calculation(emp_id,salary_slip_id):
	employee_doc = frappe.get_doc("Employee",emp_id)
			
	housing_adv_loan = 0
	sslp_doc = frappe.get_doc("Salary Slip",salary_slip_id)
	if sslp_doc.loans:
		for loan in sslp_doc.loans:
			if loan.loan_type == "Housing Advance":
				housing_adv_loan = housing_adv_loan + loan.total_payment

	if employee_doc.nationality == "Saudi Arabia" and employee_doc.added_to_gosi == 1:
		mp_cost = sslp_doc.net_pay + sslp_doc.total_loan_repayment - housing_adv_loan + ((employee_doc.basic_salary + employee_doc.housing_allowance) * 0.0975)
	else:
		mp_cost = sslp_doc.net_pay + sslp_doc.total_loan_repayment - housing_adv_loan

	return mp_cost	

@frappe.whitelist()
def create_manpower_item(month_name,year,my_in_arabic,emp_id=None,mp_qty=None,mp_cost=None):
	si_item = frappe.new_doc("Sales Invoice Item")
	si_item.item_code = 34
	si_item.description = f"Manpower cost for the month of {month_name} {year}\nتكلفة القوى العامله لشهر {my_in_arabic}"
	si_item.qty = mp_qty
	si_item.rate = mp_cost
	if emp_id:
		si_item.employee_id = emp_id
		si_item.employee_name = frappe.db.get_value("Employee", {"name":emp_id}, "employee_name")
	
	return si_item
	
#this function create manpower item for Invoices in which employees have working days and invoicing rate that fetch from PO Management
@frappe.whitelist()
def create_manpower_item_for_wdays(emp,month_name,year,my_in_arabic,emp_working_days,invoicing_rate):
	si_item = frappe.new_doc("Sales Invoice Item")
	si_item.item_code = 34
	si_item.description = f"Manpower cost for the month of {month_name} {year}\nتكلفة القوى العامله لشهر {my_in_arabic}"
	si_item.qty = emp_working_days
	si_item.rate = invoicing_rate
	si_item.employee_id = emp["employee"]
	si_item.employee_name = emp["employee_name"]

	return si_item

@frappe.whitelist()
def gosi_cost_calculation(emp_id):
	employee_doc = frappe.get_doc("Employee",emp_id)
	if employee_doc.nationality == "Saudi Arabia":
		gosi_cost = (employee_doc.basic_salary + employee_doc.housing_allowance) * 0.1175
	else:
		gosi_cost = (employee_doc.basic_salary + employee_doc.housing_allowance) * 0.02

	return gosi_cost	

@frappe.whitelist()
def create_gosi_item(month_name,year,emp_id=None,gosi_qty=None,gosi_cost=None):
	si_item = frappe.new_doc("Sales Invoice Item")
	si_item.item_code = 781
	si_item.description = f"Gosi قوسي - {month_name} {year}"
	si_item.qty = gosi_qty
	si_item.rate = gosi_cost
	if emp_id:
		si_item.employee_id = emp_id
		si_item.employee_name = frappe.db.get_value("Employee", {"name":emp_id}, "employee_name")

	return si_item

#this erc fee row contains all no of employees in qty field and erc fee from project
@frappe.whitelist()
def create_erc_fee_item(project,month_name,year,erc_fee_qty=None):
	si_item = frappe.new_doc("Sales Invoice Item")
	si_item.item_code = 415
	si_item.description = f"ERC Fees نكاليف ايليت - {month_name} {year}"
	si_item.qty = erc_fee_qty
	si_item.rate = frappe.db.get_value("Project", {"name":project}, "erc_fee")

	return si_item

#this bank transaction charges row contains all no of employees in qty field and bank transaction charges from project
@frappe.whitelist()
def create_bank_charges_item(project,month_name,year,bt_qty=None):
	si_item = frappe.new_doc("Sales Invoice Item")
	si_item.item_code = 419
	si_item.description = f"Bank Transaction التحويل البنكي - {month_name} {year}"
	si_item.qty = bt_qty
	si_item.rate = frappe.db.get_value("Project", {"name":project}, "bt_charges")

	return si_item
	
@frappe.whitelist()
def create_vat_tax():
	si_tax = frappe.new_doc("Sales Taxes and Charges")
	si_tax.charge_type = "On Net Total"
	si_tax.account_head = "VAT 15% - ERC"
	si_tax.description = "VAT 15%"
	si_tax.rate = 15

	return si_tax

@frappe.whitelist()
def update_salary_slip(emp):
	sal_slip = frappe.get_doc("Salary Slip", emp["salary_slip"])
	sal_slip.invoice_created = 1
	sal_slip.save(ignore_permissions=True)

@frappe.whitelist()
def create_payroll_processed(emp_id,month_name,project):
	pp = frappe.new_doc("Payroll Processed")
	pp.employee = emp_id
	pp.employee_name = frappe.db.get_value("Employee", {"name":emp_id}, "employee_name")
	pp.month_name = month_name
	pp.project = project
	pp.project_name = frappe.db.get_value("Project", {"name":project}, "project_name")
	pp.save(ignore_permissions=True)
Role Name
=========
nar_solidfire_sds_compliance


Description
===========
This role automates hardware and firmware compliance validations of the target hosts for NetApp SolidFire Enterprise SDS (eSDS) software. After this role successfully completes, detailed report per target host will be saved in the same directory as the playbook, unless you specify a different directory by using the sf_compliance_report_dir variable.


Requirements
============
* This role requires the target hosts to be running minimum RHEL 7.6 or other supported versions from the Interoperability Matrix (https://mysupport.NetApp.com/matrix/imt.jsp?components=97283;&solution=1757&isHWU#playground).

* This role performs compliance checks directly on each target host. So, the controller system where Ansible is run needs to have network connections to all the hosts. For more details on prerequisites for networking configuration, see the eSDS product documentation (https://docs.netapp.com/us-en/element-software/esds/concept_esds_prerequisite_tasks.html).

* This role requires Python version 3.6 or later  and Ansible version 2.10 or later.


Role Variables
==============
| Variable                 | Required | Default      |Description               | Comments                                  |
|--------------------------|----------|--------------|--------------------------|-------------------------------------------|
| sf_compliance_report_dir | no       | playbook_dir |Directory of report files | Defaults to where the playbook is located |
| sf_print_report          | no       | True         |Print report to console   | In addition to writing to report file     |


Example Playbook
================

```
---
- name: Validate compliance for SolidFire eSDS
  hosts: all
    roles:
      - role: nar_solidfire_sds_compliance
```
License
=======

GPL-3.0-only

Author Information
==================

NetApp
https://www.netapp.com

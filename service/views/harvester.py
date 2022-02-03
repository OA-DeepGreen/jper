'''
Created on 18 Nov 2015

Webpage - Graphic User Interface for an harvester 

@author: Mateusz.Kasiuba
'''
from flask import Blueprint, request, flash, redirect
from flask import render_template, abort
from flask_login import current_user

from service.__utils import jper_view_utils
from service.forms.webservice import WebserviceForm
from service.models.harvester import HarvesterModel

harvester = Blueprint('harvester', __name__)
harvesterModel = HarvesterModel()

#This is part of their code in my opinion we should move this part of code in common class
@harvester.before_request
def restrict():
    if current_user.is_anonymous:
        if not request.path.endswith('account/login'):
            return redirect('account/login')
# end part of their code should be move in common class

@harvester.route('/webservice/', defaults={'page_num': '1'}, methods=['GET','POST'])
@harvester.route('/webservice/<page_num>', methods=['GET','POST'])
def webservice(page_num):
    '''
    Page with list of webservices installed in ES database
    '''
    if not current_user.is_super:
        abort(401)

    page_num = jper_view_utils.get_req_page_num()
    webservice, num_of_pages = harvesterModel.get_webservices(int(page_num)-1)
    return render_template('harvester/webservice.html', webservice_list = webservice, num_of_pages = num_of_pages, page_num = int(page_num), name='Web Service List')


@harvester.route('/history/', defaults={'page_num': '1'}, methods=['GET','POST'])
@harvester.route('/history/<page_num>', methods=['GET','POST'])
def history(page_num):
    '''
    Page with list history quesries form harvester
    '''
    if not current_user.is_super:
        abort(401)
    page_num = jper_view_utils.get_req_page_num()
    history, num_of_pages = harvesterModel.get_history(int(page_num)-1)
    return render_template('harvester/history.html', history_list = history, num_of_pages = num_of_pages, page_num = int(page_num), name='History List')

#To consider - better it will be use MANAGE instead ADD and EDIT but at this moment idk how
#I cannot create method and link to EDIT - idk why
@harvester.route('/manage/', defaults={'webservice_id': 'add'}, methods=['GET','POST'])
@harvester.route('/manage/<webservice_id>', methods=['GET','POST'])
def manage(webservice_id):
    '''
    Page with details 
    '''
    if not current_user.is_super:
        abort(401)
    if request.method == 'POST' or webservice_id == 'add':
        form = WebserviceForm(request.form)
        name = 'Add Web Service'
    elif(webservice_id != 'add'):
        webservice = harvesterModel.get_webservice(webservice_id)
        form = WebserviceForm(harvesterModel.multidict_form_data(webservice))
        name = 'Edit Web Service'
    if request.method == 'POST' and form.validate():
        if(webservice_id != 'add'):
            harvesterModel.save_webservice(form, webservice_id)
        else:
            harvesterModel.save_webservice(form)
        flash('Record Saved', 'success')
        return redirect('/harvester/webservice')

    return render_template('harvester/manage.html', form = form, name=name)

@harvester.route('/delete/<webservice_id>', methods=['GET','POST'])
def delete(webservice_id):
    '''
    Deltete choosen webservice
    '''
    if not current_user.is_super:
        abort(401)

    harvesterModel.delete(webservice_id)
    flash('Record deleted', 'success')
    return redirect('/harvester/webservice')

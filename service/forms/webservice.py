'''
Created on 18 Nov 2015

Form for webservice

@author: Mateusz.Kasiuba
'''

from wtforms import Form, BooleanField, validators, SelectField
from wtforms import StringField as TextField
from engine.query.QueryInvoker import H_QueryInvoker
from utils.config import MULTI_PAGE, FREQUENCY_DAILY, FREQUENCY_WEEKLY, FREQUENCY_MONTHLY
from werkzeug.routing import ValidationError
import re, time, json
from datetime import datetime


def valid_url(form, url):
    try:
        if(re.findall('pageSize=\d+', form.url.data)):
            raise ValidationError(' Specify pageSize is not allowed')
        if(False == H_QueryInvoker().is_valid(MULTI_PAGE, form.url.data)):   
            raise ValidationError('0 results from %s for this engine' % MULTI_PAGE)
    except Exception as e:
        raise ValidationError('Url is wrong check it again: ' + str(e))

    return True

def valid_query(form, query):
    try:
        json.loads(form.data.query)
    except Exception as e:
        raise ValidationError('Query is wrong: ' + str(e))

    return True

def valid_date(form, date):
    """
    Private method - validate date
    
    Args:
        value - date
    
    Returns:
        Boolean
    """
    try:
        time.mktime(datetime.strptime(form.end_date.data, "%Y-%m-%d").timetuple())
    except Exception as e:
        raise ValidationError('Date is wrong: ' + str(e))

    return True

def valid_wait_window(form,wait):
    try:
        if(isinstance(form.wait_window.data,int)): 
            raise ValidationError('Should be intiger')
        if(int(form.wait_window.data) < 0):
            raise ValidationError('Should be positive')
    except Exception as e:
        raise ValidationError('Wait window is wrong: ' + str(e))

    return True


'''
Create a form for WEBSERVICE
'''
class WebserviceForm(Form):
    name = TextField('Name', [validators.Length(min=2, max=2035), validators.DataRequired()])
    url = TextField('Endpoint URL', [validators.Length(min=6, max=2035), validators.DataRequired(), valid_url])
    query = TextField('Filter Query', [validators.DataRequired()])
#     email = TextField('Email', [validators.Email()])
    email = TextField('Notification Email ')
    end_date = TextField('Start Date', [validators.DataRequired(), valid_date])
    frequency =  SelectField('Frequency', choices=[(FREQUENCY_DAILY, 'Daily'), (FREQUENCY_WEEKLY, 'Weekly'), (FREQUENCY_MONTHLY, 'Monthly')])
    engine = SelectField('Engine', choices=[(MULTI_PAGE, 'MultiPage EPMC')])
    wait_window = TextField('Article Processing Wait Window', [validators.DataRequired(), validators.number_range(0), valid_wait_window])
    active = BooleanField('Active')

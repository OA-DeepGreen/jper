'''
Created on 18 Nov 2015

Form for webservice

@author: Mateusz.Kasiuba
'''
from engine.query.QueryInvoker import H_QueryInvoker
from utils.config import MULTI_PAGE
from wtforms import Form, PasswordField, validators, RadioField
from wtforms import StringField as TextField
from werkzeug.routing import ValidationError
import re 
import time
from datetime import datetime
from service import models


def valid_url(form, url):
    try:
        if(re.findall('\pageSize=\d+', form.url.data)):
            raise ValidationError(' Specify pageSize is not allowed')
        if(False == H_QueryInvoker().is_valid(MULTI_PAGE, form.url.data)):   
            raise ValidationError('0 results from %s for this engine' % MULTI_PAGE)
    except Exception as e:
        raise ValidationError('Url is wrong check it again: ' + str(e))

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

def is_email(form, email):
    """
    Returns true if "email" is a valid email
    """
    try:
        if not re.match(r"^[A-Za-z0-9\.\+_-]+@[A-Za-z0-9\._-]+\.[a-zA-Z]*$", form.email.data):
            raise ValidationError('You must provide an email address')
    except Exception as e:
            raise ValidationError(str(e))

def valid_verify_email(form, email):
    """
    Returns true if "email" is equal the first email
    """
    try:
        if(form.email.data!=form.email_verify.data):
            raise ValidationError('Email address is not the same')
        if models.Account.pull_by_email(form.email.data) is not None:
            print('Account already exist')
            raise ValidationError('An account already exists for that email address')
    except Exception as e:
        raise ValidationError('Email is wrong check it again: ' + str(e))
    return True

def validate_password(form, email):
    """
    Verify the strength of 'password'
    Returns true if the password is strong enough
    A password is considered strong if:
        8 characters length or more
        1 digit or more
        1 uppercase letter or more
        1 lowercase letter or more
    """
    try:    
        # searching for digits
        digit_error = re.search(r"\d", form.password.data) is None
    
        # searching for uppercase
        uppercase_error = re.search(r"[A-Z]", form.password.data) is None
    
        # searching for lowercase
        lowercase_error = re.search(r"[a-z]", form.password.data) is None

        if (digit_error or uppercase_error or lowercase_error):
            raise ValidationError('The password should be 8 characters long, contain upper and lower case and at least on number')
        if(form.password.data!=form.password_verify.data):
            raise ValidationError('Password is not the same')
    except Exception as e:
        raise ValidationError(str(e))
    return True


'''
Create a form for WEBSERVICE
'''
class AdduserForm(Form):

    password_verify = PasswordField('Password verify', [validators.Length(min=8, max=2035), validators.DataRequired(), validate_password])
    password = PasswordField('Password', [validators.Length(min=8, max=2035), validators.DataRequired()])
    email = TextField('Email address', [validators.Length(min=2, max=2035), validators.DataRequired(), is_email])
    email_verify = TextField('Confirm Email address', [validators.Length(min=2, max=2035), validators.DataRequired(), valid_verify_email])
    radio = RadioField('Account type', choices=[('publisher','Publisher account'),('repository','Repository account'),('admin','Admin')])
    repository_sigel = TextField('Repository sigel (comma separated)')
    repository_bibid = TextField('Repository bibid (EZB)')
    repository_name = TextField('Repository name')
    repository_url = TextField('Repository URL')
    repository_software = TextField('Repository software')
    sword_username = TextField('Sword username')
    sword_password = TextField('Sword password')
    sword_collection = TextField('Sword collection')
    packaging = TextField('Packaging prefs (comma separated)')
    embargo_duration = TextField('Embargo duration (months) (number)')
    license_title = TextField('License title')
    license_type = TextField('License type')
    license_url = TextField('License URL')
    license_version = TextField('License version')

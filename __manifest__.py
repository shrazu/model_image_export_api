{
    'name': 'Model Image Export API',
    'summary': 'Export the images of a model with an HTTP call',

    'description': """
Model Image Export API
======================

Adds the endpoint ``POST /image_export/<model>``, to be called from a
terminal with an API key. The images of all the records of the model are
written to a folder named after the model, under the path set in the
``model_image_export_api.base_path`` system parameter. An image already on disk is only written again
when it was modified since the last export.
    """,

    'author': 'Shamim Hossen',

    'category': 'Tools',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',

    # Required modules
    'depends': [
        'base',
    ],

    # Data files
    'data': [
        'security/ir.access.csv',
        'data/ir_config_parameter.xml',
        'views/image_export_api_log_views.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}

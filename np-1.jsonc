{
    "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "triggers": {
            "Recurrence": {
                "type": "Recurrence",
                "recurrence": {
                    "frequency": "Day",
                    "interval": 1,
                    "timeZone": "UTC",
                    "schedule": {
                        "hours": [
                            9
                        ],
                        "minutes": [
                            0
                        ]
                    }
                }
            }
        },
        "actions": {
            "Query_All_Active_Service_Principals": {
                "type": "ServiceProvider",
                "inputs": {
                    "serviceProviderConfiguration": {
                        "serviceProviderId": "/serviceProviders/azurecosmosdb",
                        "operationId": "QueryDocuments",
                        "connectionName": "azurecosmosdb"
                    },
                    "parameters": {
                        "databaseId": "@appsetting('COSMOS_DB_DATABASE_ID')",
                        "containerId": "@appsetting('COSMOS_DB_CONTAINER_ID')",
                        "queryText": "SELECT c.id, c.appId, c.displayName, c.display_name, c.service_principal_id, c.appreg_object_id, c.environment, c.subscription_id, c.subscription_role, c.owners, c.passwordCredentials FROM c WHERE c.status = 'active'"
                    }
                },
                "runAfter": {}
            },
            "Inspect_Query_Response": {
                "type": "Compose",
                "inputs": "@body('Query_All_Active_Service_Principals')",
                "runAfter": {
                    "Query_All_Active_Service_Principals": [
                        "Succeeded"
                    ]
                }
            },
            "Initialize_Notified_Keys": {
                "type": "InitializeVariable",
                "inputs": {
                    "variables": [
                        {
                            "name": "NotifiedKeys",
                            "type": "array",
                            "value": []
                        }
                    ]
                },
                "runAfter": {
                    "Inspect_Query_Response": [
                        "Succeeded"
                    ]
                }
            },
            "For_Each_Service_Principal": {
                "type": "Foreach",
                "foreach": "@body('Query_All_Active_Service_Principals')?['Items']",
                "runtimeConfiguration": {
                    "concurrency": {
                        "repetitions": 5
                    }
                },
                "runAfter": {
                    "Initialize_Notified_Keys": [
                        "Succeeded"
                    ]
                },
                "actions": {
                    "Get_App_Registration_Details": {
                        "type": "Http",
                        "inputs": {
                            "uri": "https://graph.microsoft.com/v1.0/applications(appId='@{items('For_Each_Service_Principal')?['service_principal_id']}')",
                            "method": "GET",
                            "authentication": {
                                "type": "ManagedServiceIdentity",
                                "identity": "@parameters('identityAuth')",
                                "audience": "https://graph.microsoft.com"
                            }
                        },
                        "runAfter": {}
                    },
                    "Parse_App_Registration_JSON": {
                        "type": "ParseJson",
                        "runAfter": {
                            "Get_App_Registration_Details": [
                                "Succeeded",
                                "Failed"
                            ]
                        },
                        "inputs": {
                            "content": "@if(equals(outputs('Get_App_Registration_Details')?['statusCode'], 200), body('Get_App_Registration_Details'), json(concat('{\"displayName\":\"', coalesce(items('For_Each_Service_Principal')?['display_name'], items('For_Each_Service_Principal')?['id']), '\",\"appId\":\"', coalesce(items('For_Each_Service_Principal')?['service_principal_id'], 'unknown'), '\",\"passwordCredentials\":[], \"keyCredentials\":[]}')))",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "displayName": {
                                        "type": "string"
                                    },
                                    "appId": {
                                        "type": "string"
                                    },
                                    "passwordCredentials": {
                                        "type": "array"
                                    },
                                    "keyCredentials": {
                                        "type": "array"
                                    }
                                }
                            }
                        }
                    },
                    "Merge_Password_Credentials": {
                        "type": "Compose",
                        "runAfter": {
                            "Parse_App_Registration_JSON": [
                                "Succeeded"
                            ]
                        },
                        "inputs": "@if(equals(coalesce(outputs('Get_App_Registration_Details')?['statusCode'], 0), 200), coalesce(body('Parse_App_Registration_JSON')?['passwordCredentials'], createArray()), coalesce(items('For_Each_Service_Principal')?['passwordCredentials'], createArray()))"
                    },
                    "Get_App_Owners": {
                        "type": "Http",
                        "inputs": {
                            "uri": "https://graph.microsoft.com/v1.0/applications(appId='@{items('For_Each_Service_Principal')?['service_principal_id']}')/owners",
                            "method": "GET",
                            "authentication": {
                                "type": "ManagedServiceIdentity",
                                "identity": "@parameters('identityAuth')",
                                "audience": "https://graph.microsoft.com"
                            }
                        },
                        "runAfter": {
                            "Merge_Password_Credentials": [
                                "Succeeded"
                            ]
                        }
                    },
                    "Parse_Owners_JSON": {
                        "type": "Compose",
                        "runAfter": {
                            "Get_App_Owners": [
                                "Succeeded"
                            ]
                        },
                        "inputs": "@coalesce(body('Get_App_Owners')?['value'], createArray())"
                    },
                    "Parse_Owners_JSON_Fallback": {
                        "type": "Compose",
                        "runAfter": {
                            "Get_App_Owners": [
                                "Failed",
                                "TimedOut"
                            ]
                        },
                        "inputs": []
                    },
                    "Select_Owner_Emails": {
                        "type": "Select",
                        "inputs": {
                            "from": "@coalesce(outputs('Parse_Owners_JSON'), outputs('Parse_Owners_JSON_Fallback'))",
                            "select": "@item()['mail']"
                        },
                        "runAfter": {
                            "Parse_Owners_JSON": [
                                "Succeeded",
                                "Skipped"
                            ],
                            "Parse_Owners_JSON_Fallback": [
                                "Succeeded",
                                "Skipped"
                            ]
                        }
                    },
                    "Create_Owners_Email_List": {
                        "type": "Compose",
                        "inputs": "@coalesce(join(body('Select_Owner_Emails'), ';'), '')",
                        "runAfter": {
                            "Select_Owner_Emails": [
                                "Succeeded"
                            ]
                        }
                    },
                    "Filter_Valid_Owner_Emails": {
                        "type": "Query",
                        "inputs": {
                            "from": "@body('Select_Owner_Emails')",
                            "where": "@and(not(equals(item(), null)), not(equals(trim(string(item())), '')))"
                        },
                        "runAfter": {
                            "Create_Owners_Email_List": [
                                "Succeeded"
                            ]
                        }
                    },
                    "Resolve_Recipient_Emails": {
                        "type": "Compose",
                        "inputs": "@if(greater(length(body('Filter_Valid_Owner_Emails')), 0), body('Filter_Valid_Owner_Emails'), createArray('cloudazurefoundation@stellantis.com'))",
                        "runAfter": {
                            "Filter_Valid_Owner_Emails": [
                                "Succeeded"
                            ]
                        }
                    },
                    "Debug_Email_List": {
                        "type": "Compose",
                        "inputs": {
                            "EmailList": "@outputs('Create_Owners_Email_List')",
                            "ResolvedRecipients": "@outputs('Resolve_Recipient_Emails')",
                            "OwnersArray": "@coalesce(outputs('Parse_Owners_JSON'), outputs('Parse_Owners_JSON_Fallback'))",
                            "MailArray": "@body('Select_Owner_Emails')"
                        },
                        "runAfter": {
                            "Resolve_Recipient_Emails": [
                                "Succeeded"
                            ]
                        }
                    },
                    "For_Each_Password_Credential": {
                        "type": "Foreach",
                        "foreach": "@outputs('Merge_Password_Credentials')",
                        "operationOptions": "Sequential",
                        "runAfter": {
                            "Debug_Email_List": [
                                "Succeeded",
                                "Failed"
                            ]
                        },
                        "actions": {
                            "Calculate_Days_Until_Expiry": {
                                "type": "Compose",
                                "inputs": "@if(or(equals(items('For_Each_Password_Credential')?['endDateTime'], null), equals(items('For_Each_Password_Credential')?['endDateTime'], '')), int(appsetting('NO_EXPIRY_SENTINEL')), div(sub(ticks(addToTime(items('For_Each_Password_Credential')?['endDateTime'], 0, 'Second')), ticks(utcNow())), 864000000000))",
                                "runAfter": {}
                            },
                            "Determine_Notification_Category": {
                                "type": "Compose",
                                "inputs": "@if(equals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NO_EXPIRY_SENTINEL'))), 'none', if(and(greaterOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_30_DAY_WINDOW_START'))), lessOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_30_DAY_WINDOW_END')))), '30_days', if(and(greaterOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_15_DAY_WINDOW_START'))), lessOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_15_DAY_WINDOW_END')))), '15_days', if(and(greaterOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_EXPIRING_TODAY_WINDOW_START'))), lessOrEquals(int(outputs('Calculate_Days_Until_Expiry')), int(appsetting('NOTIFY_EXPIRING_TODAY_WINDOW_END')))), 'expiring_today', 'none'))))",
                                "runAfter": {
                                    "Calculate_Days_Until_Expiry": [
                                        "Succeeded"
                                    ]
                                }
                            },
                            "Build_Notification_Key": {
                                "type": "Compose",
                                "inputs": "@concat(coalesce(body('Parse_App_Registration_JSON')?['appId'], 'unknown'), '|', coalesce(items('For_Each_Password_Credential')?['keyId'], items('For_Each_Password_Credential')?['displayName'], 'unknown_credential'), '|', outputs('Determine_Notification_Category'), '|', coalesce(items('For_Each_Password_Credential')?['endDateTime'], 'no_expiry'))",
                                "runAfter": {
                                    "Determine_Notification_Category": [
                                        "Succeeded"
                                    ]
                                }
                            },
                            "Condition_Check_30_Days": {
                                "type": "If",
                                "expression": {
                                    "and": [
                                        {
                                            "equals": [
                                                "@outputs('Determine_Notification_Category')",
                                                "30_days"
                                            ]
                                        },
                                        {
                                            "equals": [
                                                "@contains(variables('NotifiedKeys'), outputs('Build_Notification_Key'))",
                                                false
                                            ]
                                        }
                                    ]
                                },
                                "actions": {
                                    "Send_30_Day_Warning_Email": {
                                        "type": "ApiConnection",
                                        "inputs": {
                                            "host": {
                                                "connection": {
                                                    "referenceName": "sendgrid"
                                                }
                                            },
                                            "method": "post",
                                            "path": "/v3/mail/send",
                                            "body": {
                                                "personalizations": [
                                                    {
                                                        "to": [
                                                            {
                                                                "email": "@{first(outputs('Resolve_Recipient_Emails'))}"
                                                            }
                                                        ],
                                                        "subject": "@{concat('FIRST REMINDER: Secret Expiring in 30 Days - ', body('Parse_App_Registration_JSON')?['displayName'])}"
                                                    }
                                                ],
                                                "from": {
                                                    "email": "@appsetting('NOTIFICATION_FROM_EMAIL')",
                                                    "name": "@appsetting('NOTIFICATION_FROM_NAME')"
                                                },
                                                "content": [
                                                    {
                                                        "type": "text/plain",
                                                        "value": "@{concat('Service Principal Secret Expiring in ~30 Days\n\nDisplay Name: ', body('Parse_App_Registration_JSON')?['displayName'], '\nApplication ID: ', body('Parse_App_Registration_JSON')?['appId'], '\nCredential Name: ', items('For_Each_Password_Credential')?['displayName'], '\nExpiry Date: ', items('For_Each_Password_Credential')?['endDateTime'], ' UTC\nDays Until Expiry: ~', outputs('Calculate_Days_Until_Expiry'), ' days\n\nRenew in Azure Portal > App Registrations > Certificates & Secrets.\n\nAutomated notification - Azure Platform Team. Contact: azure-platform-team@stellantis.com')}"
                                                    }
                                                ]
                                            }
                                        },
                                        "runAfter": {}
                                    },
                                    "Append_30_Day_Notification_Key": {
                                        "type": "AppendToArrayVariable",
                                        "inputs": {
                                            "name": "NotifiedKeys",
                                            "value": "@outputs('Build_Notification_Key')"
                                        },
                                        "runAfter": {
                                            "Send_30_Day_Warning_Email": [
                                                "Succeeded"
                                            ]
                                        }
                                    }
                                },
                                "runAfter": {
                                    "Build_Notification_Key": [
                                        "Succeeded",
                                        "Failed",
                                        "Skipped"
                                    ]
                                },
                                "else": {
                                    "actions": {
                                        "Condition_Check_15_Days": {
                                            "type": "If",
                                            "expression": {
                                                "and": [
                                                    {
                                                        "equals": [
                                                            "@outputs('Determine_Notification_Category')",
                                                            "15_days"
                                                        ]
                                                    },
                                                    {
                                                        "equals": [
                                                            "@contains(variables('NotifiedKeys'), outputs('Build_Notification_Key'))",
                                                            false
                                                        ]
                                                    }
                                                ]
                                            },
                                            "actions": {
                                                "Send_15_Day_Warning_Email": {
                                                    "type": "ApiConnection",
                                                    "inputs": {
                                                        "host": {
                                                            "connection": {
                                                                "referenceName": "sendgrid"
                                                            }
                                                        },
                                                        "method": "post",
                                                        "path": "/v3/mail/send",
                                                        "body": {
                                                            "personalizations": [
                                                                {
                                                                    "to": [
                                                                        {
                                                                            "email": "@{first(outputs('Resolve_Recipient_Emails'))}"
                                                                        }
                                                                    ],
                                                                    "subject": "@{concat('SECOND REMINDER - URGENT: Secret Expiring in 15 Days - ', body('Parse_App_Registration_JSON')?['displayName'])}"
                                                                }
                                                            ],
                                                            "from": {
                                                                "email": "@appsetting('NOTIFICATION_FROM_EMAIL')",
                                                                "name": "@appsetting('NOTIFICATION_FROM_NAME')"
                                                            },
                                                            "content": [
                                                                {
                                                                    "type": "text/plain",
                                                                    "value": "@{concat('SECOND REMINDER - URGENT: Service Principal Secret Expiring in ~15 Days\n\nDisplay Name: ', body('Parse_App_Registration_JSON')?['displayName'], '\nApplication ID: ', body('Parse_App_Registration_JSON')?['appId'], '\nCredential Name: ', items('For_Each_Password_Credential')?['displayName'], '\nExpiry Date: ', items('For_Each_Password_Credential')?['endDateTime'], ' UTC\nDays Until Expiry: ~', outputs('Calculate_Days_Until_Expiry'), ' days\n\nRenew in Azure Portal > App Registrations > Certificates & Secrets.\n\nAutomated notification - Azure Platform Team. Contact: azure-platform-team@stellantis.com')}"
                                                                }
                                                            ]
                                                        }
                                                    },
                                                    "runAfter": {}
                                                },
                                                "Append_15_Day_Notification_Key": {
                                                    "type": "AppendToArrayVariable",
                                                    "inputs": {
                                                        "name": "NotifiedKeys",
                                                        "value": "@outputs('Build_Notification_Key')"
                                                    },
                                                    "runAfter": {
                                                        "Send_15_Day_Warning_Email": [
                                                            "Succeeded"
                                                        ]
                                                    }
                                                }
                                            },
                                            "runAfter": {},
                                            "else": {
                                                "actions": {
                                                    "Condition_Check_Expiring_Today": {
                                                        "type": "If",
                                                        "expression": {
                                                            "and": [
                                                                {
                                                                    "equals": [
                                                                        "@outputs('Determine_Notification_Category')",
                                                                        "expiring_today"
                                                                    ]
                                                                },
                                                                {
                                                                    "equals": [
                                                                        "@contains(variables('NotifiedKeys'), outputs('Build_Notification_Key'))",
                                                                        false
                                                                    ]
                                                                }
                                                            ]
                                                        },
                                                        "actions": {
                                                            "Send_Expiry_Day_Email": {
                                                                "type": "ApiConnection",
                                                                "inputs": {
                                                                    "host": {
                                                                        "connection": {
                                                                            "referenceName": "sendgrid"
                                                                        }
                                                                    },
                                                                    "method": "post",
                                                                    "path": "/v3/mail/send",
                                                                    "body": {
                                                                        "personalizations": [
                                                                            {
                                                                                "to": [
                                                                                    {
                                                                                        "email": "@{first(outputs('Resolve_Recipient_Emails'))}"
                                                                                    }
                                                                                ],
                                                                                "subject": "@{concat('FINAL ALERT: Secret Expires TODAY - ', body('Parse_App_Registration_JSON')?['displayName'])}"
                                                                            }
                                                                        ],
                                                                        "from": {
                                                                            "email": "@appsetting('NOTIFICATION_FROM_EMAIL')",
                                                                            "name": "@appsetting('NOTIFICATION_FROM_NAME')"
                                                                        },
                                                                        "content": [
                                                                            {
                                                                                "type": "text/plain",
                                                                                "value": "@{concat('FINAL ALERT - CRITICAL: Service Principal Secret Expires TODAY\n\nDisplay Name: ', body('Parse_App_Registration_JSON')?['displayName'], '\nApplication ID: ', body('Parse_App_Registration_JSON')?['appId'], '\nCredential Name: ', items('For_Each_Password_Credential')?['displayName'], '\nExpiry Date: ', items('For_Each_Password_Credential')?['endDateTime'], ' UTC\nDays Until Expiry: ~', outputs('Calculate_Days_Until_Expiry'), ' days\n\nRenew in Azure Portal > App Registrations > Certificates & Secrets.\n\nAutomated notification - Azure Platform Team. Contact: azure-platform-team@stellantis.com')}"
                                                                            }
                                                                        ]
                                                                    }
                                                                },
                                                                "runAfter": {}
                                                            },
                                                            "Append_Expiry_Day_Notification_Key": {
                                                                "type": "AppendToArrayVariable",
                                                                "inputs": {
                                                                    "name": "NotifiedKeys",
                                                                    "value": "@outputs('Build_Notification_Key')"
                                                                },
                                                                "runAfter": {
                                                                    "Send_Expiry_Day_Email": [
                                                                        "Succeeded"
                                                                    ]
                                                                }
                                                            }
                                                        },
                                                        "runAfter": {},
                                                        "else": {
                                                            "actions": {
                                                                "No_Notification_Needed": {
                                                                    "type": "Compose",
                                                                    "inputs": "No notification needed - credential not in notification window",
                                                                    "runAfter": {}
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    },
    "kind": "Stateful"
}
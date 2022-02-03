from service.api import JPER


class AccTableTemplate:

    def get_fprefix(self) -> str:
        raise NotImplementedError()

    def get_table_schema(self) -> dict:
        raise NotImplementedError()

    def list_data(self, since, page=None, page_size=None, ) -> dict:
        raise NotImplementedError()


class MatchedTableTemplate(AccTableTemplate):
    # Matching table/csv for providers (with detailed reasoning)

    def __init__(self, is_provider=False, repository_id=None):
        self.is_provider = is_provider
        self.repository_id = repository_id

    def get_fprefix(self) -> str:
        return "matched"

    def get_table_schema(self) -> dict:
        return {
            "screen": ["Analysis Date", "ISSN or EISSN", "DOI", "License", "Forwarded to {EZB-Id}", "Term",
                       "Appears in {notification_field}"],
            "header": ["Analysis Date", "ISSN or EISSN", "DOI", "License", "Forwarded to", "Term", "Appears in"],
            "Analysis Date": "matches[*].created_date",
            "ISSN or EISSN": "matches[*].alliance.issn",
            "DOI": "matches[*].alliance.doi",
            "License": "matches[*].alliance.link",
            "Forwarded to": "matches[*].bibid",
            "Term": "matches[*].provenance[0].term",
            "Appears in": "matches[*].provenance[0].notification_field"
        }

    def list_data(self, since, page=None, page_size=None) -> dict:
        mlist = JPER.list_matches(since, page=page, page_size=page_size,
                                  repository_id=self.repository_id,
                                  provider=self.is_provider)
        return mlist.data


class NotificationTableTemplate(AccTableTemplate):
    # Notification table/csv for repositories

    def __init__(self, is_provider=False, repository_id=None):
        self.is_provider = is_provider
        self.repository_id = repository_id

    def get_fprefix(self) -> str:
        return "routed"

    def get_table_schema(self) -> dict:
        return {
            "screen": ["Send Date", ["DOI", "Publisher"], ["Publication Date", "Embargo"], "Title", "Analysis Date"],
            "header": ["Send Date", "DOI", "Publisher", "Publication Date", "Embargo", "Title", "Analysis Date"],
            "Analysis Date": "notifications[*].analysis_date",
            "Send Date": "notifications[*].created_date",
            "Embargo": "notifications[*].embargo.duration",
            "DOI": "notifications[*].metadata.identifier[?(@.type=='doi')].id",
            "Publisher": "notifications[*].metadata.publisher",
            "Title": "notifications[*].metadata.title",
            "Publication Date": "notifications[*].metadata.publication_date"
        }

    def list_data(self, since, page=None, page_size=None) -> dict:
        nlist = JPER.list_notifications(since, page=page, page_size=page_size,
                                        repository_id=self.repository_id,
                                        provider=self.is_provider, )
        return nlist.data


class FailedNotificationTableTemplate(AccTableTemplate):
    # Rejected table/csv for providers

    def __init__(self, provider_id=None):
        self.provider_id = provider_id

    def get_fprefix(self) -> str:
        return "failed"

    def get_table_schema(self) -> dict:
        return {
            "screen": ["Send Date", "ISSN or EISSN", "DOI", "Reason", "Analysis Date"],
            "header": ["Send Date", "ISSN or EISSN", "DOI", "Reason", "Analysis Date"],
            "Send Date": "failed[*].created_date",
            "Analysis Date": "failed[*].analysis_date",
            "ISSN or EISSN": "failed[*].issn_data",
            "DOI": "failed[*].metadata.identifier[?(@.type=='doi')].id",
            "Reason": "failed[*].reason"
        }

    def list_data(self, since, page=None, page_size=None) -> dict:
        flist = JPER.list_failed(since, page=page, page_size=page_size,
                                 provider_id=self.provider_id)
        return flist.data

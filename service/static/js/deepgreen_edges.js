deepg = {
    templates: {
        newAdminSearch: function (params) {
            return edges.instantiate(deepg.templates.AdminSearch, params, edges.newTemplate);
        },
        AdminSearch: function (params) {

        }

    }
}


jQuery(document).ready(function ($) {

    //////////////////////////////////////////////////////
    // test loading static files

    var countFormat = edges.numFormat({
        thousandsSeparator: ","
    });

    var _components = [
        // edges.newFullSearchController({
        //     id: "search-controller",
        //     category: "controller",
        //     sortOptions: [
        //         {field: "index.asciiunpunctitle.exact", display: "Title"},
        //         {field: "index.publisher.exact", display: "Publisher"}
        //     ],
        //     fieldOptions: [
        //         {field: "index.unpunctitle", display: "Title"},
        //         {field: "index.publisher", display: "Publisher"}
        //     ]
        // }),
        // edges.newFullSearchController(),
        // edges.newPager({
        //     id: "result-count",
        //     category: "pager",
        //     renderer: edges.bs3.newResultCountRenderer({
        //         countFormat: countFormat,
        //         suffix: " indexed journals",
        //         htmlContainerWrapper: false
        //     })
        // }),

        edges.newRefiningANDTermSelector({
            id: "publisher",
            field: "index.publisher.exact",
            display: "Publisher",
            size: 10,
            category: "facet"
        }),
        edges.newRefiningANDTermSelector({
            id: "subject",
            field: "index.classification.exact",
            display: "Subject",
            size: 10,
            category: "facet"
        }),
        // edges.newORTermSelector({
        //     id: "country",
        //     field : "index.country.exact",
        //     display: "Country",
        //     size: 200,
        //     category: "facet",
        //     renderer : edges.bs3.newORTermSelectorRenderer({
        //         showCount: true
        //     })
        // }),
        edges.newFullSearchController({
            id: "search-controller",
            category: "controller",
            sortOptions : [
                {field: "index.asciiunpunctitle.exact", display: "Title"},
                {field: "index.publisher.exact", display: "Publisher"}
            ],
            fieldOptions : [
                {field: "index.unpunctitle", display: "Title"},
                {field: "index.publisher", display: "Publisher"}
            ]
        }),
        edges.newSelectedFilters({
            id: "selected-filters",
            category: "selected-filters",
            fieldDisplays : {
                "index.publisher.exact" : "Publisher",
                "index.classification.exact" : "Classification",
                "index.country.exact" : "Country"
            }
        }),
        edges.newSearchingNotification({
            id: "searching-notification",
            category: "searching-notification"
        }),
        edges.newPager({
            id: "top-pager",
            category: "top-pager"
        }),
        edges.newPager({
            id: "bottom-pager",
            category: "bottom-pager"
        }),
        edges.newSearchingNotification({
            id: "searching-notification",
            category: "searching-notification"
        }),
        edges.newResultsDisplay({
            id: "results",
            category: "results",
            renderer : edges.bs3.newResultsDisplayRenderer({
                fieldDisplayMap: [
                    {field: "id", display: "ID"},
                    {field: "bibjson.title", display: "Title"}
                ]
            })
        }),
    ]

    var eg = edges.newEdge({
        selector: "#public-journal-search",
        search_url: "https://doaj.org/query/journal/_search?ref=public_journal",
        // template: doaj.templates.newPublicSearch({
        //     title: "Journals"
        // }),
        template: edges.bs3.newFacetview(),
        // baseQuery : es.newQuery({
        //     must: [es.newTermFilter({field: "index.classification.exact", value: "Medicine"})]
        // }),
        openingQuery: es.newQuery({
            sort: [{"field" : "created_date", "order" : "desc"}],
            size: 50
        }),
        components: _components,
    });
    // eg.loadStaticsAsync()
})



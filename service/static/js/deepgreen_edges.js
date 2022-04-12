$.extend(true, dgcore, {

    initSearchUi: function (settings) {

        var _components = [
            // edges.newPager({
            //     id: "result-count",
            //     category: "pager",
            //     renderer: edges.bs3.newResultCountRenderer({
            //         countFormat: countFormat,
            //         suffix: " indexed journals",
            //         htmlContainerWrapper: false
            //     })
            // }),

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
            settings.result_display,
        ]
        _components.push(...(settings.opt_components || []))

        var eg = edges.newEdge({
            selector: "#gd-edges-main",
            search_url: settings.search_url,
            template: edges.bs3.newFacetview(),
            // baseQuery : es.newQuery({
            //     must: [es.newTermFilter({field: "index.classification.exact", value: "Medicine"})]
            // }),
            openingQuery: es.newQuery({
                sort: [{"field": "created_date", "order": "desc"}],
                size: 50
            }),
            components: _components,
        });
    }

})





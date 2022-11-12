$.extend(true, dgcore, {
   activeEdges: false,
    initCommonSearchUi: function (settings) {

        var _components = [
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

        dgcore.activeEdges = edges.newEdge({
            selector: "#gd-edges-main",
            search_url: settings.search_url,
            template: edges.bs3.newFacetview(),
            openingQuery: es.newQuery({
                sort: [{"field": "created_date", "order": "desc"}],
                size: 50
            }),
            components: _components,
        });
    }

})





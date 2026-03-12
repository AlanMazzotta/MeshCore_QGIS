def classFactory(iface):
    from .meshcore_plugin import MeshCoreViewshedPlugin
    return MeshCoreViewshedPlugin(iface)

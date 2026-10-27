# License: MIT License
from io import StringIO

import pytest
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.debug_backend import BasicBackend


def dash_lengths(backend, handle):
    return [
        (end - start).magnitude
        for kind, *data in backend.collector
        if kind == "line"
        for start, end, properties in [data]
        if properties.handle == handle
    ]


@pytest.mark.parametrize("layout_flags", [0, 1, 2, 3])
@pytest.mark.parametrize("viewport_scale", [0.5, 1.0, 2.0])
@pytest.mark.parametrize("entity_type", ["LINE", "LWPOLYLINE"])
@pytest.mark.parametrize("global_scale,entity_scale", [(1.0, 1.0), (2.0, 3.0)])
def test_viewport_dash_lengths(
    layout_flags, viewport_scale, entity_type, global_scale, entity_scale
):
    doc = ezdxf.new()
    doc.header["$LTSCALE"] = global_scale
    # The document header describes the current layout, not every paper layout.
    doc.header["$PSLTSCALE"] = 1 - (layout_flags & 1)
    doc.linetypes.new("DASH", dxfattribs={"pattern": [2.0, 1.0, -1.0]})
    attribs = {"linetype": "DASH", "ltscale": entity_scale}
    msp = doc.modelspace()
    if entity_type == "LINE":
        entity = msp.add_line((-40, 0), (40, 0), dxfattribs=attribs)
    else:
        entity = msp.add_lwpolyline([(-40, 0), (40, 0)], dxfattribs=attribs)
    handle = entity.dxf.handle
    paper = doc.layouts.new("Paper")
    paper.dxf.layout_flags = layout_flags
    paper.add_viewport(
        center=(0, 0),
        size=(200, 100),
        view_center_point=(0, 0),
        view_height=100 / viewport_scale,
        status=2,
    )
    paper_line = paper.add_line((-40, -1), (40, -1), dxfattribs=attribs)
    paper_handle = paper_line.dxf.handle
    stream = StringIO()
    doc.write(stream)
    doc = ezdxf.read(StringIO(stream.getvalue()))

    backend = BasicBackend()
    frontend = Frontend(RenderContext(doc), backend)
    frontend.draw_layout(doc.layouts.get("Paper"), finalize=False)
    expected = global_scale * entity_scale
    if not layout_flags & 1:
        expected *= viewport_scale
    lengths = dash_lengths(backend, handle)
    assert lengths
    assert lengths[0] == pytest.approx(expected)
    assert max(lengths) == pytest.approx(expected)
    assert dash_lengths(backend, paper_handle)[0] == pytest.approx(
        global_scale * entity_scale
    )

    # Reusing the same frontend outside a viewport must reset its scaling.
    backend.clear()
    frontend.draw_layout(doc.modelspace(), finalize=False)
    assert dash_lengths(backend, handle)[0] == pytest.approx(
        global_scale * entity_scale
    )


def test_dotted_pattern_cache_across_layouts():
    doc = ezdxf.new()
    doc.linetypes.new("DOT", dxfattribs={"pattern": [1.0, 0.0, -1.0]})
    entity = doc.modelspace().add_line(
        (-40, 0), (40, 0), dxfattribs={"linetype": "DOT", "ltscale": 2.0}
    )
    for name, flags in [("Model units", 0), ("Paper units", 1)]:
        paper = doc.layouts.new(name)
        paper.dxf.layout_flags = flags
        paper.add_viewport(
            center=(0, 0),
            size=(200, 100),
            view_center_point=(0, 0),
            view_height=200,
            status=2,
        )
    backend = BasicBackend()
    frontend = Frontend(RenderContext(doc), backend)
    frontend.draw_layout(doc.layouts.get("Model units"), finalize=False)
    assert dash_lengths(backend, entity.dxf.handle)[0] == pytest.approx(0.05)

    # Both effective pattern scales are 1, but their minimum dot lengths differ.
    entity.dxf.ltscale = 1.0
    backend.clear()
    frontend.draw_layout(doc.layouts.get("Paper units"), finalize=False)
    assert dash_lengths(backend, entity.dxf.handle)[0] == pytest.approx(0.1)


def test_small_viewport_uses_bounded_scale():
    doc = ezdxf.new()
    doc.linetypes.new("DASH", dxfattribs={"pattern": [2.0, 1.0, -1.0]})
    entity = doc.modelspace().add_line(
        (-40, 0), (40, 0), dxfattribs={"linetype": "DASH"}
    )
    paper = doc.layouts.new("Paper")
    paper.dxf.layout_flags = 0
    paper.add_viewport(
        center=(0, 0),
        size=(200, 100),
        view_center_point=(0, 0),
        view_height=100 / 0.00001,
        status=2,
    )
    backend = BasicBackend()
    Frontend(RenderContext(doc), backend).draw_layout(paper)
    # Retain the pipeline's 1:10000 rendering limit for very small viewports.
    assert dash_lengths(backend, entity.dxf.handle)[0] == pytest.approx(0.0001)


if __name__ == "__main__":
    pytest.main([__file__])

import fitz
import numpy as np

from app.vector_pdf import extract_page, segments, tokens


def drawing():
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    shape = page.new_shape()
    for i in range(31):
        shape.draw_line((20,20+i*10), (250,20+i*10))
    shape.finish(width=.5,closePath=False)
    shape.commit()
    page.insert_text((40,60), 'U1 LM358', fontsize=10)
    return doc, page


def test_exact_native_lines_and_words_are_in_rendered_pixel_space():
    doc,page = drawing()
    native = extract_page(page, dpi=144)
    assert native.primitive_count == 31
    assert native.lines[0] == (40,40,500,40,1)
    assert [t.text for t in tokens(native)] == ['U1','LM358']
    assert len(segments(native)) == 31
    doc.close()


def test_native_threshold_does_not_promote_raster_or_sparse_decoration():
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect((20,20,200,200))
    page.insert_text((40,60),'R1 10k')
    assert extract_page(page) is None
    doc.close()


def test_pdf_rotation_and_deskew_map_text_and_geometry_together():
    doc,page = drawing()
    page.set_rotation(90)
    native = extract_page(page,dpi=72)
    assert native.lines[0][:4] == (380,20,380,250)
    assert all(t.vertical for t in tokens(native))
    moved = native.transformed([[2,0,3],[0,2,5]])
    assert moved.lines[0][:4] == (763,45,763,505)
    assert np.allclose(moved.text[0]['bbox'], np.array(native.text[0]['bbox'])*2+[3,5,3,5])
    doc.close()


def test_unfilled_pin_bubble_is_not_a_junction_dot():
    doc,page = drawing()
    page.draw_circle((100,100),2,color=(0,0,0),fill=None)
    page.draw_circle((150,100),2,color=(0,0,0),fill=(0,0,0))
    native = extract_page(page,dpi=72)
    assert len(native.dots)==1
    assert native.dots[0] == (150,100,2)
    doc.close()


def test_only_collinear_touching_primitives_coalesce():
    from app.vector_pdf import VectorPage
    native=VectorPage(lines=[(0,10,10,10,1),(10,10,20,10,1),(0,12,20,12,1),(25,10,30,10,1)])
    lines=segments(native)
    assert sorted((s.y0,s.x0,s.x1) for s in lines)==[(10,0,20),(10,25,30),(12,0,20)]


def test_stroked_native_text_is_not_promoted_to_wire_segments():
    from app.vector_pdf import VectorPage
    native=VectorPage(lines=[(20,20,25,20,1),(20,20,20,30,1),(0,25,100,25,1)],
                      text=[{'text':'U1','bbox':(19,19,35,32),'direction':(1,0)}])
    result=segments(native)
    assert len(result)==1 and result[0].x0==0 and result[0].x1==100

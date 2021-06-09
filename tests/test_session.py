import pytest
import pyama.session.model as pysm
import pyama.session.controller as pysc
import pyama.session.view_tk as pysvtk
class TestSession:
    @pytest.fixture
    def Controller(self):
        return pysc.SessionController()
    @pytest.fixture
    def View(self, Controller):
        view = pysvtk.SessionView_Tk(Controller.title, Controller.control_queue, Controller.status)
        Controller.view = view
        return view

    def test_session_initialization(self):
        session = pysm.SessionModel()
        assert isinstance(session, pysm.SessionModel)
    def test_controller_initialization(self, Controller):
        assert isinstance(Controller, pysc.SessionController)
    def test_view_initialization(self, Controller, View):
        assert isinstance(View, pysvtk.SessionView_Tk)
        assert Controller.view == View
